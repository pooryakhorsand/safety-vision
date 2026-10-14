import numpy as np

from engine.identity.recent_gallery import RecentGallery
from engine.perception.reid import HistogramEmbedder, TrackCrops, average_embedding, cut_crop, is_good_crop, normalize
from engine.tests.conftest import at, make_config, scene


def vec(*values):
    return normalize(np.array(values, dtype=np.float32))[0]


def gallery(neighbors=None, window=10):
    cfg = make_config(reid={"neighbor_cameras": neighbors or {}, "merge_threshold": 0.8, "max_templates": 3}).reid
    return RecentGallery(cfg, window)


def test_similar_vector_in_the_window_matches():
    g = gallery()
    g.add("u1", 1, "ppe", "no_helmet", 5, vec(1, 0, 0))
    g.close("u1", at(10))
    match = g.find(1, "ppe", "no_helmet", 9, vec(0.95, 0.1, 0), at(70))
    assert match.uid == "u1" and match.similarity > 0.9 and match.track_ids == [5]


def test_different_person_does_not_match():
    g = gallery()
    g.add("u1", 1, "ppe", "no_helmet", 5, vec(1, 0, 0))
    g.close("u1", at(10))
    assert g.find(1, "ppe", "no_helmet", 9, vec(0, 1, 0), at(70)) is None


def test_after_the_window_no_match_and_entry_is_dropped():
    g = gallery(window=10)
    g.add("u1", 1, "ppe", "no_helmet", 5, vec(1, 0, 0))
    g.close("u1", at(0))
    assert g.find(1, "ppe", "no_helmet", 9, vec(1, 0, 0), at(11 * 60)) is None
    assert len(g) == 0


def test_two_people_on_screen_together_are_never_merged():
    g = gallery()
    g.add("u1", 1, "ppe", "no_helmet", 5, vec(1, 0, 0))  # still open, track 5 on screen
    g.set_visible(1, {5, 9})
    assert g.find(1, "ppe", "no_helmet", 9, vec(1, 0, 0), at(5)) is None
    g.set_visible(1, {9})  # track 5 left the picture
    assert g.find(1, "ppe", "no_helmet", 9, vec(1, 0, 0), at(6)).uid == "u1"


def test_other_event_type_or_module_is_not_compared():
    g = gallery()
    g.add("u1", 1, "ppe", "no_vest", 5, vec(1, 0, 0))
    g.close("u1", at(1))
    assert g.find(1, "ppe", "no_helmet", 9, vec(1, 0, 0), at(5)) is None
    assert g.find(1, "other", "no_vest", 9, vec(1, 0, 0), at(5)) is None


def test_neighbour_camera_only_when_configured():
    plain = gallery()
    plain.add("u1", 2, "ppe", "no_helmet", 5, vec(1, 0, 0))
    plain.close("u1", at(1))
    assert plain.find(1, "ppe", "no_helmet", 9, vec(1, 0, 0), at(5)) is None
    linked = gallery({1: [2]})
    linked.add("u1", 2, "ppe", "no_helmet", 5, vec(1, 0, 0))
    linked.close("u1", at(1))
    assert linked.find(1, "ppe", "no_helmet", 9, vec(1, 0, 0), at(5)).uid == "u1"


def test_reopen_updates_entry_and_caps_templates():
    g = gallery()
    g.add("u1", 1, "ppe", "no_helmet", 5, vec(1, 0, 0))
    g.close("u1", at(1))
    for i in range(5):
        g.reopen("u1", 6 + i, 2 + i, vec(1, 0.1 * i, 0))
    entry = g._entries["u1"]
    assert len(entry.templates) == 3 and entry.closed_at is None and entry.occurrences == 6
    assert entry.track_ids[:2] == [5, 6]


def test_histogram_embedder_same_colours_match_different_do_not():
    embedder = HistogramEmbedder()
    red_a = cut_crop(scene([((0, 0, 60, 160), (0, 0, 255))], size=(160, 60)), (0, 0, 60, 160))
    red_b = cut_crop(scene([((0, 0, 40, 100), (10, 10, 250))], size=(100, 40)), (0, 0, 40, 100))
    blue = cut_crop(scene([((0, 0, 40, 100), (255, 0, 0))], size=(100, 40)), (0, 0, 40, 100))
    vectors = embedder.embed([red_a, red_b, blue])
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)
    assert vectors[0] @ vectors[1] > 0.9 and vectors[0] @ vectors[2] < 0.3
    assert abs(np.linalg.norm(average_embedding(vectors)) - 1.0) < 1e-5


def test_good_crop_rules():
    size = (640, 480)
    assert is_good_crop(size, (100, 100, 200, 300), [], 96)
    assert not is_good_crop(size, (100, 100, 200, 150), [], 96)  # too small
    assert not is_good_crop(size, (0, 100, 100, 300), [], 96)  # cut by the left edge
    assert not is_good_crop(size, (100, 100, 200, 300), [(110, 110, 210, 310)], 96)  # covered by someone
    assert is_good_crop(size, (100, 100, 200, 300), [(400, 100, 500, 300)], 96)


def test_track_crops_keep_only_the_latest():
    crops = TrackCrops(2)
    for i in range(4):
        crops.add(1, i)
    assert crops.get(1) == [2, 3]
    crops.forget_except(set())
    assert crops.get(1) == []
