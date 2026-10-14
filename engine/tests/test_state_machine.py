from engine.core.frame import Observation
from engine.events.state_machine import MergeTarget, StateMachine, to_payload
from engine.tests.conftest import at, make_config

EVENTS = make_config().events  # confirm 1s, clear 1s, grace 0.3s, merge window 10 min


def obs(active=True, track=1, event_type="no_helmet", conf=0.9):
    return Observation(track, event_type, active, conf, (0, 0, 10, 10), [], module="ppe")


def run(machine, steps):
    """steps = [(seconds, [observations])] -> flat list of actions"""
    actions = []
    for seconds, observations in steps:
        actions += machine.process(at(seconds), observations)
    return actions


def ticks(start, stop, observation, step=0.1):
    n = int(round((stop - start) / step))
    return [(start + i * step, [observation]) for i in range(n + 1)]


def test_flicker_shorter_than_confirm_time_makes_no_event():
    machine = StateMachine(1, EVENTS)
    actions = run(machine, ticks(0, 0.6, obs()) + [(0.7, []), (2.0, [])])
    assert actions == [] and machine.open_count == 0


def test_stable_violation_makes_one_create_then_one_end():
    machine = StateMachine(1, EVENTS)
    actions = run(machine, ticks(0, 3, obs()) + ticks(3.1, 4.5, obs(active=False)))
    assert [a.kind for a in actions] == ["create", "end"]
    create, end = actions
    assert create.uid == end.uid and create.occurrences == 1
    assert create.at == at(0)  # starts when the violation began, not when confirmed
    assert end.at == at(3.0)  # ends when it was last seen


def test_short_gap_inside_the_grace_time_does_not_restart_the_timer():
    machine = StateMachine(1, EVENTS)
    steps = ticks(0, 0.4, obs()) + [(0.5, []), (0.6, [])] + ticks(0.7, 1.5, obs())
    actions = run(machine, steps)
    assert [a.kind for a in actions] == ["create"] and actions[0].at == at(0)


def test_same_person_violating_again_reopens_the_same_event():
    machine = StateMachine(1, EVENTS)
    steps = ticks(0, 2, obs()) + [(3.5, [])] + ticks(10, 12, obs())
    actions = run(machine, steps)
    assert [a.kind for a in actions] == ["create", "end", "reopen"]
    assert actions[0].uid == actions[2].uid and actions[2].occurrences == 2


def test_different_event_types_and_people_are_separate_cases():
    machine = StateMachine(1, EVENTS)
    both = [obs(track=1), obs(track=2), obs(track=1, event_type="no_vest")]
    actions = run(machine, [(i * 0.5, both) for i in range(6)])
    assert len(actions) == 3 and len({a.uid for a in actions}) == 3


def test_resolver_match_reopens_an_earlier_event_of_a_new_track():
    target = MergeTarget("old-uid", 2, [5], 0.9)
    machine = StateMachine(1, EVENTS, resolver=lambda observation, now: target)
    actions = run(machine, ticks(0, 1.5, obs(track=9)))
    assert actions[0].kind == "reopen" and actions[0].uid == "old-uid"
    assert actions[0].occurrences == 3 and actions[0].track_ids == [5, 9] and actions[0].merged_similarity == 0.9


def test_resolver_is_asked_only_once_per_new_track():
    asked = []
    machine = StateMachine(1, EVENTS, resolver=lambda o, now: asked.append(o.track_id))
    run(machine, ticks(0, 2, obs()) + [(3.5, [])] + ticks(10, 12, obs()))
    assert asked == [1]  # the second violation of track 1 reopens without asking


def test_ended_case_is_forgotten_after_the_merge_window():
    machine = StateMachine(1, EVENTS)
    run(machine, ticks(0, 2, obs()) + [(3.5, [])])
    assert machine._cases
    machine.process(at(3.5 + 11 * 60), [])
    assert not machine._cases


def test_close_all_ends_open_events():
    machine = StateMachine(1, EVENTS)
    run(machine, ticks(0, 2, obs()))
    actions = machine.close_all(at(2.1))
    assert [a.kind for a in actions] == ["end"] and machine.open_count == 0


def test_payloads_match_the_api():
    machine = StateMachine(1, EVENTS, resolver=lambda o, n: MergeTarget("u", 1, [3], 0.8123))
    create = StateMachine(1, EVENTS)
    c = run(create, ticks(0, 1.5, obs()))[0]
    payload = to_payload(c)
    assert payload["event_type"] == "no_helmet" and payload["camera_id"] == 1 and payload["occurrences"] == 1
    assert payload["started_at"].startswith("2026-01-01T10:00:00") and payload["extra"]["track_ids"] == [1]
    r = run(machine, ticks(0, 1.5, obs(track=7)))[0]
    reopened = to_payload(r)
    assert reopened["ended_at"] is None and reopened["occurrences"] == 2
    assert reopened["extra"] == {"track_ids": [3, 7], "merged_similarity": 0.812}
    end = StateMachine(1, EVENTS)
    e = run(end, ticks(0, 1.5, obs()) + [(3.0, [])])[-1]
    assert set(to_payload(e)) == {"uid", "ended_at", "last_seen_at"}
