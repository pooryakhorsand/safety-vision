import cv2
import numpy as np

from engine.core.frame import FrameContext, Label, Observation, Track
from engine.events.snapshot import make_snapshot
from engine.render.overlay import FrameRenderer, Overlay, output_size
from engine.tests.conftest import at, det, make_config, scene


def make_ctx(size=(1080, 1920)):
    ctx = FrameContext(1, "CAM-01", 0, at(0), scene([((300, 200, 500, 800), (120, 120, 120))], size=size))
    ctx.persons = [Track(1, (300, 200, 500, 800), 0.9), Track(2, (320, 210, 520, 810), 0.9)]
    ctx.detections["equipment"] = [det("no_helmet", (340, 200, 420, 260))]
    labels = [Label("no_helmet", True), Label("vest", False)]
    ctx.observations = [Observation(1, "no_helmet", True, 0.9, ctx.persons[0].box, labels, module="ppe")]
    return ctx


def test_output_size_is_never_larger_and_always_even():
    assert output_size(1920, 1080, 1280) == (1280, 720)
    assert output_size(720, 1280, 1280) == (720, 1280)
    assert output_size(641, 481, 1280) == (640, 480)
    w, h = output_size(1919, 1079, 1000)
    assert w % 2 == 0 and h % 2 == 0 and max(w, h) <= 1000


def test_renderer_draws_on_a_copy_and_keeps_the_original():
    cfg = make_config()
    ctx = make_ctx()
    original = ctx.image.copy()
    picture = FrameRenderer(cfg).render(ctx)
    assert picture.shape == (720, 1280, 3)
    assert np.array_equal(ctx.image, original)  # detection never sees the overlay
    assert picture.sum() != cv2.resize(original, (1280, 720)).sum()


def test_colours_follow_the_item_and_has_or_missing():
    overlay = Overlay(640, 480, make_config())
    assert overlay.label_color("helmet") == (255, 150, 40)
    assert overlay.label_color("no_helmet") == (70, 70, 255)
    assert overlay.label_color("no_vest") == (0, 220, 255)
    assert overlay.label_color("mystery") == (90, 220, 90)


def test_tags_of_overlapping_people_do_not_overlap():
    overlay = Overlay(1280, 720, make_config())
    image = np.zeros((720, 1280, 3), np.uint8)
    occupied = []
    for i in range(3):
        overlay.person(image, (400 + i * 5, 300 + i * 3, 520, 700), i, [Label("no_helmet", True)], occupied)
    for i, a in enumerate(occupied):
        for b in occupied[i + 1 :]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_snapshot_is_a_limited_size_jpeg_with_the_person_marked():
    cfg = make_config(events={"snapshot_max_side": 960})
    ctx = make_ctx()
    data = make_snapshot(ctx, 1, ctx.persons[0].box, [Label("no_helmet", True)], cfg)
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert max(image.shape[:2]) == 960
    assert data[:2] == b"\xff\xd8"
