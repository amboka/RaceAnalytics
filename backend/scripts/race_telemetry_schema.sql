-- Race telemetry schema
-- Target: PostgreSQL

BEGIN;

-- One row per incoming message across all topics.
-- record_id is the stable join key to topic-specific tables.
CREATE TABLE IF NOT EXISTS telemetry_identity (
  record_id BIGSERIAL PRIMARY KEY,
  race_id TEXT NOT NULL,
  frame_id TEXT NOT NULL,
  ts_ns BIGINT NOT NULL,
  topic_name TEXT NOT NULL,
  source_seq BIGINT NOT NULL DEFAULT -1,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (race_id, topic_name, ts_ns, frame_id, source_seq)
);

CREATE INDEX IF NOT EXISTS ix_identity_race_ts
  ON telemetry_identity (race_id, ts_ns);

CREATE INDEX IF NOT EXISTS ix_identity_topic_ts
  ON telemetry_identity (topic_name, ts_ns);

CREATE TABLE IF NOT EXISTS topic_state_estimation (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  x_m DOUBLE PRECISION,
  y_m DOUBLE PRECISION,
  z_m DOUBLE PRECISION,
  roll_rad DOUBLE PRECISION,
  pitch_rad DOUBLE PRECISION,
  yaw_rad DOUBLE PRECISION,
  wx_radps DOUBLE PRECISION,
  wy_radps DOUBLE PRECISION,
  wz_radps DOUBLE PRECISION,
  vx_mps DOUBLE PRECISION,
  vy_mps DOUBLE PRECISION,
  vz_mps DOUBLE PRECISION,
  omega_w_fl DOUBLE PRECISION,
  omega_w_fr DOUBLE PRECISION,
  omega_w_rl DOUBLE PRECISION,
  omega_w_rr DOUBLE PRECISION,
  v_mps DOUBLE PRECISION,
  v_raw_mps DOUBLE PRECISION,
  ax_mps2 DOUBLE PRECISION,
  ay_mps2 DOUBLE PRECISION,
  az_mps2 DOUBLE PRECISION,
  yaw_vel_rad DOUBLE PRECISION,
  kappa_radpm DOUBLE PRECISION,
  dbeta_radps DOUBLE PRECISION,
  ddyaw_radps2 DOUBLE PRECISION,
  ax_vel_mps2 DOUBLE PRECISION,
  ay_vel_mps2 DOUBLE PRECISION,
  lambda_fl_perc DOUBLE PRECISION,
  lambda_fr_perc DOUBLE PRECISION,
  lambda_rl_perc DOUBLE PRECISION,
  lambda_rr_perc DOUBLE PRECISION,
  valid_wheelsspeeds_b BOOLEAN,
  alpha_fl_rad DOUBLE PRECISION,
  alpha_fr_rad DOUBLE PRECISION,
  alpha_rl_rad DOUBLE PRECISION,
  alpha_rr_rad DOUBLE PRECISION,
  diff_fr_alpha_rad DOUBLE PRECISION,
  delta_wheel_rad DOUBLE PRECISION,
  timestamp DOUBLE PRECISION,
  gas DOUBLE PRECISION,
  brake DOUBLE PRECISION,
  clutch DOUBLE PRECISION,
  gear DOUBLE PRECISION,
  rpm DOUBLE PRECISION,
  front_brake_pressure DOUBLE PRECISION,
  rear_brake_pressure DOUBLE PRECISION,
  vehicle_timestamp DOUBLE PRECISION,
  cba_actual_pressure_fl_pa DOUBLE PRECISION,
  cba_actual_pressure_fr_pa DOUBLE PRECISION,
  cba_actual_pressure_rl_pa DOUBLE PRECISION,
  cba_actual_pressure_rr_pa DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_cba_status_fl (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  cba_actual_pressure_fl_pa DOUBLE PRECISION,
  cba_actual_pressure_fl DOUBLE PRECISION,
  cba_target_pressure_fl_ack DOUBLE PRECISION,
  cba_actual_current_fl_a DOUBLE PRECISION,
);

CREATE TABLE IF NOT EXISTS topic_cba_status_fr (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  cba_actual_pressure_fr_pa DOUBLE PRECISION,
  cba_actual_pressure_fr DOUBLE PRECISION,
  cba_target_pressure_fr_ack DOUBLE PRECISION,
  cba_actual_current_fr_a DOUBLE PRECISION,
);

CREATE TABLE IF NOT EXISTS topic_cba_status_rl (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  cba_actual_pressure_rl_pa DOUBLE PRECISION,
  cba_actual_pressure_rl DOUBLE PRECISION,
  cba_target_pressure_rl_ack DOUBLE PRECISION,
  cba_actual_current_rl_a DOUBLE PRECISION,
);

CREATE TABLE IF NOT EXISTS topic_cba_status_rr (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  cba_actual_pressure_rr_pa DOUBLE PRECISION,
  cba_actual_pressure_rr DOUBLE PRECISION,
  cba_target_pressure_rr_ack DOUBLE PRECISION,
  cba_actual_current_rr_a DOUBLE PRECISION,
);

CREATE TABLE IF NOT EXISTS topic_hl_msg_01 (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  hl_alive_01 SMALLINT,
  hl_target_pressure_rr DOUBLE PRECISION,
  hl_target_pressure_rl DOUBLE PRECISION,
  hl_target_pressure_fr DOUBLE PRECISION,
  hl_target_pressure_fl DOUBLE PRECISION,
  hl_target_gear SMALLINT,
  hl_target_throttle DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_hl_msg_02 (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  hl_alive_02 SMALLINT,
  hl_psa_mode_of_operation SMALLINT,
  hl_target_psa_control DOUBLE PRECISION,
  hl_psa_profile_acc_rad_s2 INTEGER,
  hl_psa_profile_dec_rad_s2 INTEGER,
  hl_psa_profile_vel_rad_s INTEGER
);

CREATE TABLE IF NOT EXISTS topic_psa_status_01 (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  psa_actual_pos_rad DOUBLE PRECISION,
  psa_actual_speed_rad_s DOUBLE PRECISION,
  psa_actual_torque_m_nm DOUBLE PRECISION,
  psa_actual_mode_of_operation SMALLINT,
  psa_actual_current_a DOUBLE PRECISION,
  psa_actual_voltage_v DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_psa_status_02 (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  psa_target_psa_control_ack DOUBLE PRECISION,
  psa_actual_pos DOUBLE PRECISION,
  psa_actual_speed DOUBLE PRECISION,
  psa_actual_torque DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_wheels_speed_01 (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  wss_speed_fl_rad_s DOUBLE PRECISION,
  wss_speed_fr_rad_s DOUBLE PRECISION,
  wss_speed_rl_rad_s DOUBLE PRECISION,
  wss_speed_rr_rad_s DOUBLE PRECISION
);



CREATE TABLE IF NOT EXISTS topic_ice_status_01 (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  ice_actual_gear DOUBLE PRECISION,
  ice_target_gear_ack DOUBLE PRECISION,
  ice_actual_throttle DOUBLE PRECISION,
  ice_target_throttle_ack DOUBLE PRECISION,
  ice_push_to_pass_req DOUBLE PRECISION,
  ice_push_to_pass_ack DOUBLE PRECISION,
  ice_water_press_k_pa DOUBLE PRECISION,
  ice_available_fuel_l DOUBLE PRECISION,
  ice_downshift_available DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_ice_status_02 (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  ice_oil_temp_deg_c DOUBLE PRECISION,
  ice_engine_speed_rpm DOUBLE PRECISION,
  ice_fuel_press_k_pa DOUBLE PRECISION,
  ice_water_temp_deg_c DOUBLE PRECISION,
  ice_oil_press_k_pa DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_badenia_560_tpms_front (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  tpr4_temp_fl DOUBLE PRECISION,
  tpr4_temp_fr DOUBLE PRECISION,
  tpr4_abs_press_fr DOUBLE PRECISION,
  tpr4_abs_press_fl DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_badenia_560_tpms_rear (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  tpr4_temp_rl DOUBLE PRECISION,
  tpr4_temp_rr DOUBLE PRECISION,
  tpr4_abs_press_rl DOUBLE PRECISION,
  tpr4_abs_press_rr DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_badenia_560_tyre_surface_temp_front (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  outer_fl DOUBLE PRECISION,
  center_fl DOUBLE PRECISION,
  inner_fl DOUBLE PRECISION,
  outer_fr DOUBLE PRECISION,
  center_fr DOUBLE PRECISION,
  inner_fr DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS topic_badenia_560_tyre_surface_temp_rear (
  record_id BIGINT PRIMARY KEY REFERENCES telemetry_identity(record_id) ON DELETE CASCADE,
  outer_rl DOUBLE PRECISION,
  center_rl DOUBLE PRECISION,
  inner_rl DOUBLE PRECISION,
  outer_rr DOUBLE PRECISION,
  center_rr DOUBLE PRECISION,
  inner_rr DOUBLE PRECISION
);

COMMIT;
