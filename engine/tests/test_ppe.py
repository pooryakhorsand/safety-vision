from engine.core.frame import FrameContext, Track
from engine.modules.base import MODULE_REGISTRY, create_modules
from engine.modules.ppe.association import assign_equipment, split_name
from engine.modules.ppe.module import PpeModule
from engine.modules.ppe.voting import BAD, OK, PpeVoter
from engine.tests.conftest import at, det, make_config

PPE = make_config().modules.ppe


def eq(name, box, conf=0.9):
    return (name, conf, tuple(float(v) for v in box))


def test_split_name():
    assert split_name("no_helmet", PPE.missing_prefixes) == ("helmet", True)
    assert split_name("Helmet", PPE.missing_prefixes) == ("helmet", False)


def test_helmet_goes_to_the_person_it_is_on():
    persons = [(1, (100, 100, 200, 400)), (2, (400, 100, 500, 400))]
    out = assign_equipment(persons, [eq("helmet", (130, 100, 170, 140))], PPE)
    assert list(out) == [1]


def test_overlapping_people_one_item_goes_to_one_person_only():
    persons = [(1, (100, 100, 220, 400)), (2, (160, 100, 280, 400))]
    helmet = eq("helmet", (190, 105, 240, 145))  # lies inside both boxes
    out = assign_equipment(persons, [helmet], PPE)
    assert sum(len(v) for v in out.values()) == 1


def test_item_in_the_wrong_body_zone_is_rejected():
    persons = [(1, (100, 100, 200, 400))]
    assert assign_equipment(persons, [eq("helmet", (130, 340, 170, 380))], PPE) == {}  # helmet on the feet
    assert 1 in assign_equipment(persons, [eq("shoe", (120, 350, 180, 395))], PPE)


def test_item_mostly_outside_the_box_is_rejected():
    persons = [(1, (100, 100, 200, 400))]
    assert assign_equipment(persons, [eq("helmet", (180, 100, 260, 140))], PPE) == {}


def test_voting_does_not_flip_on_one_or_two_noisy_frames():
    cfg = make_config(modules={"ppe": {"vote_window": 15, "min_votes": 4}}).modules.ppe
    voter = PpeVoter(cfg)
    for i in range(6):
        voter.update(1, [eq("helmet", (0, 0, 1, 1))], i)
    assert voter.update(1, [eq("no_helmet", (0, 0, 1, 1))], 6)["helmet"] == OK
    assert voter.update(1, [eq("no_helmet", (0, 0, 1, 1))], 7)["helmet"] == OK
    assert voter.update(1, [], 8)["helmet"] == OK


def test_voting_switches_after_enough_frames_and_ties_are_violations():
    cfg = make_config(modules={"ppe": {"vote_window": 8, "min_votes": 3}}).modules.ppe
    voter = PpeVoter(cfg)
    for i in range(3):
        state = voter.update(1, [eq("helmet", (0, 0, 1, 1))], i)
    assert state["helmet"] == OK
    for i in range(3, 6):
        state = voter.update(1, [eq("no_helmet", (0, 0, 1, 1))], i)
    assert state["helmet"] == BAD  # 3 ok vs 3 bad -> tie -> violation


def test_stale_tracks_are_forgotten():
    voter = PpeVoter(PPE)
    voter.update(1, [eq("helmet", (0, 0, 1, 1))], 0)
    voter.forget_stale(1000)
    assert 1 not in voter._state


def make_ctx(persons, equipment, frame_index=0):
    ctx = FrameContext(1, "CAM-01", frame_index, at(frame_index * 0.1), None)
    ctx.persons = [Track(i, box, 0.9) for i, box in persons]
    ctx.detections["equipment"] = [det(n, b) for n, b in equipment]
    return ctx


def test_module_reports_missing_helmet_and_ok_vest():
    module = PpeModule(make_config(), 1)
    box = (100, 100, 200, 400)
    observations = []
    for i in range(3):
        observations = module.process(
            make_ctx([(1, box)], [("no_helmet", (130, 100, 170, 140)), ("vest", (110, 180, 190, 280))], i)
        )
    by_type = {o.event_type: o for o in observations}
    assert by_type["no_helmet"].active and not by_type["no_vest"].active
    assert {label.name for label in by_type["no_helmet"].labels} == {"no_helmet", "vest"}
    assert by_type["no_helmet"].confidence == 0.9


def test_shoe_and_boot_share_one_event_type():
    module = PpeModule(make_config(), 1)
    box = (100, 100, 200, 400)
    for i in range(3):
        obs = module.process(make_ctx([(1, box)], [("no_shoe", (120, 350, 180, 395))], i))
    assert [o.event_type for o in obs] == ["no_safety_shoes"] and obs[0].active


def test_registry_and_per_camera_module_choice():
    assert "ppe" in MODULE_REGISTRY
    assert [m.key for m in create_modules(["ppe"], make_config(), 1)] == ["ppe"]
    assert create_modules(["unknown"], make_config(), 1) == []
