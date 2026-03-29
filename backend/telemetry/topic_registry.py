"""Registry of ROS topics to Django models and field mappings.

This module is the single source of truth for ingestion:
- which ROS topic goes to which model/table
- which message fields are extracted
- how source message paths map to model columns
"""

from dataclasses import dataclass
from typing import Dict, Type

from django.db import models as dj_models

from .models import (
    TopicBadenia560TpmsFront,
    TopicBadenia560TpmsRear,
    TopicBadenia560TyreSurfaceTempFront,
    TopicBadenia560TyreSurfaceTempRear,
    TopicCbaStatusFl,
    TopicCbaStatusFr,
    TopicCbaStatusRl,
    TopicCbaStatusRr,
    TopicHlMsg01,
    TopicHlMsg02,
    TopicIceStatus01,
    TopicIceStatus02,
    TopicKistlerAccBody,
    TopicKistlerAngVelBody,
    TopicKistlerCorrevit,
    TopicPsaStatus01,
    TopicPsaStatus02,
    TopicStateEstimation,
    TopicTfTransform,
    TopicWheelsSpeed01,
)


@dataclass(frozen=True)
class TopicSpec:
    topic: str
    message_type: str
    model: Type[dj_models.Model]
    field_map: Dict[str, str]
    repeated: bool = False


# Base identity fields used for TelemetryIdentity row creation.
# Values describe where each field comes from in ingest code.
IDENTITY_FIELD_SOURCE = {
    "race_id": "runtime.race_id",
    "frame_id": "msg.header.frame_id",
    "ts_ns": "msg.header.stamp -> ns (fallback: bag_timestamp)",
    "topic_name": "topic",
    "source_seq": "msg.header.seq (fallback: -1)",
}


TOPIC_REGISTRY: Dict[str, TopicSpec] = {
    "/constructor0/state_estimation": TopicSpec(
        topic="/constructor0/state_estimation",
        message_type="StateEstimation",
        model=TopicStateEstimation,
        field_map={ 
            "x_m": "x_m",
            "y_m": "y_m",
            "z_m": "z_m",
            "roll_rad": "roll_rad",
            "pitch_rad": "pitch_rad",
            "yaw_rad": "yaw_rad",
            "wx_radps": "wx_radps",
            "wy_radps": "wy_radps",
            "wz_radps": "wz_radps",
            "vx_mps": "vx_mps",
            "vy_mps": "vy_mps",
            "vz_mps": "vz_mps",
            "omega_w_fl": "omega_w_fl",
            "omega_w_fr": "omega_w_fr",
            "omega_w_rl": "omega_w_rl",
            "omega_w_rr": "omega_w_rr",
            "v_mps": "v_mps",
            "v_raw_mps": "v_raw_mps",
            "ax_mps2": "ax_mps2",
            "ay_mps2": "ay_mps2",
            "az_mps2": "az_mps2",
            "yaw_vel_rad": "yaw_vel_rad",
            "kappa_radpm": "kappa_radpm",
            "dbeta_radps": "dbeta_radps",
            "ddyaw_radps2": "ddyaw_radps2",
            "ax_vel_mps2": "ax_vel_mps2",
            "ay_vel_mps2": "ay_vel_mps2",
            "lambda_fl_perc": "lambda_fl_perc",
            "lambda_fr_perc": "lambda_fr_perc",
            "lambda_rl_perc": "lambda_rl_perc",
            "lambda_rr_perc": "lambda_rr_perc",
            "valid_wheelsspeeds_b": "valid_wheelsspeeds_b",
            "alpha_fl_rad": "alpha_fl_rad",
            "alpha_fr_rad": "alpha_fr_rad",
            "alpha_rl_rad": "alpha_rl_rad",
            "alpha_rr_rad": "alpha_rr_rad",
            "diff_fr_alpha_rad": "diff_fr_alpha_rad",
            "delta_wheel_rad": "delta_wheel_rad",
            "timestamp": "timestamp",
            "gas": "gas",
            "brake": "brake",
            "clutch": "clutch",
            "gear": "gear",
            "rpm": "rpm",
            "front_brake_pressure": "front_brake_pressure",
            "rear_brake_pressure": "rear_brake_pressure",
            "vehicle_timestamp": "vehicle_timestamp",
            "cba_actual_pressure_fl_pa": "cba_actual_pressure_fl_pa",
            "cba_actual_pressure_fr_pa": "cba_actual_pressure_fr_pa",
            "cba_actual_pressure_rl_pa": "cba_actual_pressure_rl_pa",
            "cba_actual_pressure_rr_pa": "cba_actual_pressure_rr_pa",
        },
    ),
    "/tf": TopicSpec(
        topic="/tf",
        message_type="TFMessage",
        model=TopicTfTransform,
        repeated=True,
        field_map={
            "transforms[].header.frame_id": "parent_frame_id",
            "transforms[].child_frame_id": "child_frame_id",
            "transforms[].header.stamp": "stamp_ns",
            "transforms[].transform.translation.x": "translation_x",
            "transforms[].transform.translation.y": "translation_y",
            "transforms[].transform.translation.z": "translation_z",
            "transforms[].transform.rotation.x": "rotation_x",
            "transforms[].transform.rotation.y": "rotation_y",
            "transforms[].transform.rotation.z": "rotation_z",
            "transforms[].transform.rotation.w": "rotation_w",
            "transforms[] index": "transform_index",
        },
    ),
    "/constructor0/can/cba_status_fl": TopicSpec(
        topic="/constructor0/can/cba_status_fl",
        message_type="CbaStatusFl",
        model=TopicCbaStatusFl,
        field_map={
            "cba_actual_pressure_fl_pa": "cba_actual_pressure_fl_pa",
            "cba_actual_pressure_fl": "cba_actual_pressure_fl",
            "cba_target_pressure_fl_ack": "cba_target_pressure_fl_ack",
            "cba_actual_current_fl_a": "cba_actual_current_fl_a",
            "cba_voltage_fl_v": "cba_voltage_fl_v",
        },
    ),
    "/constructor0/can/cba_status_fr": TopicSpec(
        topic="/constructor0/can/cba_status_fr",
        message_type="CbaStatusFr",
        model=TopicCbaStatusFr,
        field_map={
            "cba_actual_pressure_fr_pa": "cba_actual_pressure_fr_pa",
            "cba_actual_pressure_fr": "cba_actual_pressure_fr",
            "cba_target_pressure_fr_ack": "cba_target_pressure_fr_ack",
            "cba_actual_current_fr_a": "cba_actual_current_fr_a",
            "cba_voltage_fr_v": "cba_voltage_fr_v",
        },
    ),
    "/constructor0/can/cba_status_rl": TopicSpec(
        topic="/constructor0/can/cba_status_rl",
        message_type="CbaStatusRl",
        model=TopicCbaStatusRl,
        field_map={
            "cba_actual_pressure_rl_pa": "cba_actual_pressure_rl_pa",
            "cba_actual_pressure_rl": "cba_actual_pressure_rl",
            "cba_target_pressure_rl_ack": "cba_target_pressure_rl_ack",
            "cba_actual_current_rl_a": "cba_actual_current_rl_a",
            "cba_voltage_rl_v": "cba_voltage_rl_v",
        },
    ),
    "/constructor0/can/cba_status_rr": TopicSpec(
        topic="/constructor0/can/cba_status_rr",
        message_type="CbaStatusRr",
        model=TopicCbaStatusRr,
        field_map={
            "cba_actual_pressure_rr_pa": "cba_actual_pressure_rr_pa",
            "cba_actual_pressure_rr": "cba_actual_pressure_rr",
            "cba_target_pressure_rr_ack": "cba_target_pressure_rr_ack",
            "cba_actual_current_rr_a": "cba_actual_current_rr_a",
            "cba_voltage_rr_v": "cba_voltage_rr_v",
        },
    ),
    "/constructor0/can/hl_msg_01": TopicSpec(
        topic="/constructor0/can/hl_msg_01",
        message_type="HLMsg01",
        model=TopicHlMsg01,
        field_map={
            "hl_alive_01": "hl_alive_01",
            "hl_target_pressure_rr": "hl_target_pressure_rr",
            "hl_target_pressure_rl": "hl_target_pressure_rl",
            "hl_target_pressure_fr": "hl_target_pressure_fr",
            "hl_target_pressure_fl": "hl_target_pressure_fl",
            "hl_target_gear": "hl_target_gear",
            "hl_target_throttle": "hl_target_throttle",
        },
    ),
    "/constructor0/can/hl_msg_02": TopicSpec(
        topic="/constructor0/can/hl_msg_02",
        message_type="HLMsg02",
        model=TopicHlMsg02,
        field_map={
            "hl_alive_02": "hl_alive_02",
            "hl_psa_mode_of_operation": "hl_psa_mode_of_operation",
            "hl_target_psa_control": "hl_target_psa_control",
            "hl_psa_profile_acc_rad_s2": "hl_psa_profile_acc_rad_s2",
            "hl_psa_profile_dec_rad_s2": "hl_psa_profile_dec_rad_s2",
            "hl_psa_profile_vel_rad_s": "hl_psa_profile_vel_rad_s",
        },
    ),
    "/constructor0/can/psa_status_01": TopicSpec(
        topic="/constructor0/can/psa_status_01",
        message_type="PSAStatus01",
        model=TopicPsaStatus01,
        field_map={
            "psa_actual_pos_rad": "psa_actual_pos_rad",
            "psa_actual_speed_rad_s": "psa_actual_speed_rad_s",
            "psa_actual_torque_m_nm": "psa_actual_torque_m_nm",
            "psa_actual_mode_of_operation": "psa_actual_mode_of_operation",
            "psa_actual_current_a": "psa_actual_current_a",
            "psa_actual_voltage_v": "psa_actual_voltage_v",
        },
    ),
    "/constructor0/can/psa_status_02": TopicSpec(
        topic="/constructor0/can/psa_status_02",
        message_type="PSAStatus02",
        model=TopicPsaStatus02,
        field_map={
            "psa_target_psa_control_ack": "psa_target_psa_control_ack",
            "psa_actual_pos": "psa_actual_pos",
            "psa_actual_speed": "psa_actual_speed",
            "psa_actual_torque": "psa_actual_torque",
        },
    ),
    "/constructor0/can/wheels_speed_01": TopicSpec(
        topic="/constructor0/can/wheels_speed_01",
        message_type="WheelsSpeed01",
        model=TopicWheelsSpeed01,
        field_map={
            "wss_speed_fl_rad_s": "wss_speed_fl_rad_s",
            "wss_speed_fr_rad_s": "wss_speed_fr_rad_s",
            "wss_speed_rl_rad_s": "wss_speed_rl_rad_s",
            "wss_speed_rr_rad_s": "wss_speed_rr_rad_s",
        },
    ),
    "/constructor0/can/kistler_acc_body": TopicSpec(
        topic="/constructor0/can/kistler_acc_body",
        message_type="KistlerAccBody",
        model=TopicKistlerAccBody,
        field_map={
            "acc_x_body": "acc_x_body",
            "acc_y_body": "acc_y_body",
            "acc_z_body": "acc_z_body",
        },
    ),
    "/constructor0/can/kistler_ang_vel_body": TopicSpec(
        topic="/constructor0/can/kistler_ang_vel_body",
        message_type="KistlerAngVelBody",
        model=TopicKistlerAngVelBody,
        field_map={
            "ang_vel_x_body": "ang_vel_x_body",
            "ang_vel_y_body": "ang_vel_y_body",
            "ang_vel_z_body": "ang_vel_z_body",
        },
    ),
    "/constructor0/can/kistler_correvit": TopicSpec(
        topic="/constructor0/can/kistler_correvit",
        message_type="KistlerCorrevit",
        model=TopicKistlerCorrevit,
        field_map={
            "vel_x_cor": "vel_x_cor",
            "vel_y_cor": "vel_y_cor",
            "vel_cor": "vel_cor",
            "angle_cor": "angle_cor",
        },
    ),
    "/constructor0/can/ice_status_01": TopicSpec(
        topic="/constructor0/can/ice_status_01",
        message_type="ICEStatus01",
        model=TopicIceStatus01,
        field_map={
            "ice_actual_gear": "ice_actual_gear",
            "ice_target_gear_ack": "ice_target_gear_ack",
            "ice_actual_throttle": "ice_actual_throttle",
            "ice_target_throttle_ack": "ice_target_throttle_ack",
            "ice_push_to_pass_req": "ice_push_to_pass_req",
            "ice_push_to_pass_ack": "ice_push_to_pass_ack",
            "ice_water_press_k_pa": "ice_water_press_k_pa",
            "ice_available_fuel_l": "ice_available_fuel_l",
            "ice_downshift_available": "ice_downshift_available",
        },
    ),
    "/constructor0/can/ice_status_02": TopicSpec(
        topic="/constructor0/can/ice_status_02",
        message_type="ICEStatus02",
        model=TopicIceStatus02,
        field_map={
            "ice_oil_temp_deg_c": "ice_oil_temp_deg_c",
            "ice_engine_speed_rpm": "ice_engine_speed_rpm",
            "ice_fuel_press_k_pa": "ice_fuel_press_k_pa",
            "ice_water_temp_deg_c": "ice_water_temp_deg_c",
            "ice_oil_press_k_pa": "ice_oil_press_k_pa",
        },
    ),
    "/constructor0/can/badenia_560_tpms_front": TopicSpec(
        topic="/constructor0/can/badenia_560_tpms_front",
        message_type="Badenia560TpmsFront",
        model=TopicBadenia560TpmsFront,
        field_map={
            "tpr4_temp_fl": "tpr4_temp_fl",
            "tpr4_temp_fr": "tpr4_temp_fr",
            "tpr4_abs_press_fr": "tpr4_abs_press_fr",
            "tpr4_abs_press_fl": "tpr4_abs_press_fl",
        },
    ),
    "/constructor0/can/badenia_560_tpms_rear": TopicSpec(
        topic="/constructor0/can/badenia_560_tpms_rear",
        message_type="Badenia560TpmsRear",
        model=TopicBadenia560TpmsRear,
        field_map={
            "tpr4_temp_rl": "tpr4_temp_rl",
            "tpr4_temp_rr": "tpr4_temp_rr",
            "tpr4_abs_press_rl": "tpr4_abs_press_rl",
            "tpr4_abs_press_rr": "tpr4_abs_press_rr",
        },
    ),
    "/constructor0/can/badenia_560_tyre_surface_temp_front": TopicSpec(
        topic="/constructor0/can/badenia_560_tyre_surface_temp_front",
        message_type="Badenia560TyreSurfaceTempFront",
        model=TopicBadenia560TyreSurfaceTempFront,
        field_map={
            "outer_fl": "outer_fl",
            "center_fl": "center_fl",
            "inner_fl": "inner_fl",
            "outer_fr": "outer_fr",
            "center_fr": "center_fr",
            "inner_fr": "inner_fr",
        },
    ),
    "/constructor0/can/badenia_560_tyre_surface_temp_rear": TopicSpec(
        topic="/constructor0/can/badenia_560_tyre_surface_temp_rear",
        message_type="Badenia560TyreSurfaceTempRear",
        model=TopicBadenia560TyreSurfaceTempRear,
        field_map={
            "outer_rl": "outer_rl",
            "center_rl": "center_rl",
            "inner_rl": "inner_rl",
            "outer_rr": "outer_rr",
            "center_rr": "center_rr",
            "inner_rr": "inner_rr",
        },
    ),
}


def get_topic_spec(topic_name: str) -> TopicSpec | None:
    return TOPIC_REGISTRY.get(topic_name)
