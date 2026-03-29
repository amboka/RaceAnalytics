from django.test import Client, TestCase

from analysis.lapTime import _hardcoded_part_metrics
from telemetry.models import TelemetryIdentity, TopicStateEstimation


class StateEstimationMixin:
    def _create_state_estimation(
        self,
        race_id: str,
        ts_ns: int,
        *,
        speed_mps: float,
        x_m: float | None = None,
        y_m: float | None = None,
        ax_mps2: float | None = None,
        ay_mps2: float | None = None,
        pressure_pa: float = 0.0,
        slip_angle_rad: float = 0.0,
        slip_ratio_perc: float = 0.0,
    ) -> None:
        identity = TelemetryIdentity.objects.create(
            race_id=race_id,
            frame_id="base_link",
            ts_ns=ts_ns,
            topic_name="/constructor0/state_estimation",
        )
        TopicStateEstimation.objects.create(
            record=identity,
            x_m=x_m,
            y_m=y_m,
            v_mps=speed_mps,
            ax_mps2=ax_mps2,
            ay_mps2=ay_mps2,
            alpha_fl_rad=slip_angle_rad,
            alpha_fr_rad=slip_angle_rad,
            alpha_rl_rad=slip_angle_rad,
            alpha_rr_rad=slip_angle_rad,
            lambda_fl_perc=slip_ratio_perc,
            lambda_fr_perc=slip_ratio_perc,
            lambda_rl_perc=slip_ratio_perc,
            lambda_rr_perc=slip_ratio_perc,
            cba_actual_pressure_fl_pa=pressure_pa,
            cba_actual_pressure_fr_pa=pressure_pa,
            cba_actual_pressure_rl_pa=pressure_pa,
            cba_actual_pressure_rr_pa=pressure_pa,
        )


class TopSpeedEndpointTests(StateEstimationMixin, TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_top_speed_returns_max_speed_for_each_race(self) -> None:
        self._create_state_estimation("race-a", 1, speed_mps=42.1)
        self._create_state_estimation("race-a", 2, speed_mps=48.7)
        self._create_state_estimation("race-b", 3, speed_mps=51.2)
        self._create_state_estimation("race-b", 4, speed_mps=49.9)

        response = self.client.get("/api/topSpeed")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "topSpeeds": [
                    {"race_id": "race-a", "top_speed_mps": 48.7},
                    {"race_id": "race-b", "top_speed_mps": 51.2},
                ]
            },
        )


class TimeLostPerSectionEndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_time_lost_per_section_returns_slow_minus_fast_for_each_section(self) -> None:
        response = self.client.get("/api/timeLostPerSection")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "timeLostPerSection": {
                    "snake": 3684062533,
                    "long": 1438238604,
                    "corner": 1961693766,
                }
            },
        )


class BrakingEfficiencyEndpointTests(StateEstimationMixin, TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.bounds = {
            "slow": _hardcoded_part_metrics("slow"),
            "fast": _hardcoded_part_metrics("fast"),
        }

    def _seed_braking_section(
        self,
        race_id: str,
        section: str,
        speeds: list[float],
        pressure_pa: float,
        x_offset: float,
    ) -> None:
        start_ns = self.bounds[race_id][section]["start_ns"]
        assert start_ns is not None

        for index, speed in enumerate(speeds):
            self._create_state_estimation(
                race_id=race_id,
                ts_ns=int(start_ns + index * 1_000_000_000),
                x_m=x_offset + index * 10.0,
                y_m=0.0,
                speed_mps=speed,
                ax_mps2=-6.0,
                pressure_pa=pressure_pa,
            )

    def test_braking_efficiency_returns_overall_score_and_section_breakdown(self) -> None:
        self._seed_braking_section("slow", "snake", [60.0, 50.0, 40.0, 30.0, 25.0], 360_000.0, 0.0)
        self._seed_braking_section("fast", "snake", [60.0, 50.0, 40.0, 30.0], 300_000.0, 0.0)

        self._seed_braking_section("slow", "long", [58.0, 48.0, 38.0, 28.0, 23.0], 340_000.0, 1_000.0)
        self._seed_braking_section("fast", "long", [58.0, 48.0, 38.0, 26.0], 300_000.0, 1_000.0)

        self._seed_braking_section("slow", "corner", [55.0, 45.0, 35.0, 25.0], 330_000.0, 2_000.0)
        self._seed_braking_section("fast", "corner", [55.0, 45.0, 32.0], 300_000.0, 2_000.0)

        response = self.client.get("/api/brakingEfficiency")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["brakingEfficiency"]

        self.assertEqual(payload["raceId"], "slow")
        self.assertEqual(payload["referenceRaceId"], "fast")
        self.assertEqual(payload["sectionCount"], 3)
        self.assertIn(payload["weakestSection"], {"snake", "long", "corner"})
        self.assertGreater(payload["score"], 0)
        self.assertLess(payload["score"], 100)
        self.assertEqual(payload["timeLostUnderBraking"]["value"], 3_000_000_000)

        sections = {section["section"]: section for section in payload["sections"]}
        self.assertEqual(set(sections.keys()), {"snake", "long", "corner"})
        self.assertEqual(sections["snake"]["time_lost"]["value"], 1_000_000_000)
        self.assertEqual(sections["long"]["time_lost"]["value"], 1_000_000_000)
        self.assertEqual(sections["corner"]["time_lost"]["value"], 1_000_000_000)
        self.assertEqual({section["status"] for section in sections.values()}, {"ok"})


class GripUtilizationEndpointTests(StateEstimationMixin, TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.bounds = {
            "slow": _hardcoded_part_metrics("slow"),
            "fast": _hardcoded_part_metrics("fast"),
        }

    def _seed_grip_section(
        self,
        race_id: str,
        section: str,
        *,
        lateral_accel_mps2: float,
        speed_mps: float,
        slip_angle_rad: float,
        slip_ratio_perc: float,
        sample_count: int,
    ) -> None:
        start_ns = self.bounds[race_id][section]["start_ns"]
        assert start_ns is not None

        for index in range(sample_count):
            self._create_state_estimation(
                race_id=race_id,
                ts_ns=int(start_ns + index * 1_000_000_000),
                speed_mps=speed_mps,
                ay_mps2=lateral_accel_mps2,
                slip_angle_rad=slip_angle_rad,
                slip_ratio_perc=slip_ratio_perc,
            )

    def test_grip_utilization_returns_overall_score_and_underutilization_breakdown(self) -> None:
        self._seed_grip_section(
            "fast",
            "snake",
            lateral_accel_mps2=10.0,
            speed_mps=40.0,
            slip_angle_rad=0.030,
            slip_ratio_perc=2.0,
            sample_count=4,
        )
        self._seed_grip_section(
            "slow",
            "snake",
            lateral_accel_mps2=8.5,
            speed_mps=35.0,
            slip_angle_rad=0.020,
            slip_ratio_perc=1.8,
            sample_count=4,
        )

        self._seed_grip_section(
            "fast",
            "long",
            lateral_accel_mps2=9.0,
            speed_mps=37.0,
            slip_angle_rad=0.026,
            slip_ratio_perc=2.0,
            sample_count=4,
        )
        self._seed_grip_section(
            "slow",
            "long",
            lateral_accel_mps2=7.0,
            speed_mps=30.0,
            slip_angle_rad=0.018,
            slip_ratio_perc=1.9,
            sample_count=4,
        )

        self._seed_grip_section(
            "fast",
            "corner",
            lateral_accel_mps2=9.5,
            speed_mps=28.0,
            slip_angle_rad=0.028,
            slip_ratio_perc=2.2,
            sample_count=4,
        )
        self._seed_grip_section(
            "slow",
            "corner",
            lateral_accel_mps2=8.0,
            speed_mps=26.0,
            slip_angle_rad=0.019,
            slip_ratio_perc=2.0,
            sample_count=4,
        )

        response = self.client.get("/api/gripUtilization")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["gripUtilization"]

        self.assertEqual(payload["raceId"], "slow")
        self.assertEqual(payload["referenceRaceId"], "fast")
        self.assertEqual(payload["overallStatus"], "underutilizing_grip")
        self.assertEqual(payload["sectionCount"], 3)
        self.assertEqual(payload["weakestSection"], "long")
        self.assertGreater(payload["score"], 0)
        self.assertLess(payload["score"], 100)

        sections = {section["section"]: section for section in payload["sections"]}
        self.assertEqual(set(sections.keys()), {"snake", "long", "corner"})
        self.assertEqual({section["status"] for section in sections.values()}, {"underutilizing_grip"})
        self.assertLess(sections["long"]["score"], sections["snake"]["score"])
        self.assertLess(sections["long"]["ratios"]["cornering_load"], 1.0)
        self.assertLess(sections["long"]["ratios"]["corner_speed"], 1.0)
