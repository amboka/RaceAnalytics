from django.db import models


class TelemetryIdentity(models.Model):
	record_id = models.BigAutoField(primary_key=True)
	race_id = models.TextField()
	frame_id = models.TextField()
	ts_ns = models.BigIntegerField()
	topic_name = models.TextField()
	source_seq = models.BigIntegerField(default=-1)
	ingested_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		db_table = "telemetry_identity"
		constraints = [
			models.UniqueConstraint(
				fields=["race_id", "topic_name", "ts_ns", "frame_id", "source_seq"],
				name="uq_identity_race_topic_ts_frame_seq",
			)
		]
		indexes = [
			models.Index(fields=["race_id", "ts_ns"], name="ix_identity_race_ts"),
			models.Index(fields=["topic_name", "ts_ns"], name="ix_identity_topic_ts"),
			models.Index(fields=["race_id", "topic_name", "ts_ns"], name="ix_identity_race_topic_ts"),
		]


class TopicStateEstimation(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_state_estimation",
	)
	x_m = models.FloatField(null=True)
	y_m = models.FloatField(null=True)
	z_m = models.FloatField(null=True)
	roll_rad = models.FloatField(null=True)
	pitch_rad = models.FloatField(null=True)
	yaw_rad = models.FloatField(null=True)
	wx_radps = models.FloatField(null=True)
	wy_radps = models.FloatField(null=True)
	wz_radps = models.FloatField(null=True)
	vx_mps = models.FloatField(null=True)
	vy_mps = models.FloatField(null=True)
	vz_mps = models.FloatField(null=True)
	omega_w_fl = models.FloatField(null=True)
	omega_w_fr = models.FloatField(null=True)
	omega_w_rl = models.FloatField(null=True)
	omega_w_rr = models.FloatField(null=True)
	v_mps = models.FloatField(null=True)
	v_raw_mps = models.FloatField(null=True)
	ax_mps2 = models.FloatField(null=True)
	ay_mps2 = models.FloatField(null=True)
	az_mps2 = models.FloatField(null=True)
	yaw_vel_rad = models.FloatField(null=True)
	kappa_radpm = models.FloatField(null=True)
	dbeta_radps = models.FloatField(null=True)
	ddyaw_radps2 = models.FloatField(null=True)
	ax_vel_mps2 = models.FloatField(null=True)
	ay_vel_mps2 = models.FloatField(null=True)
	lambda_fl_perc = models.FloatField(null=True)
	lambda_fr_perc = models.FloatField(null=True)
	lambda_rl_perc = models.FloatField(null=True)
	lambda_rr_perc = models.FloatField(null=True)
	valid_wheelsspeeds_b = models.BooleanField(null=True)
	alpha_fl_rad = models.FloatField(null=True)
	alpha_fr_rad = models.FloatField(null=True)
	alpha_rl_rad = models.FloatField(null=True)
	alpha_rr_rad = models.FloatField(null=True)
	diff_fr_alpha_rad = models.FloatField(null=True)
	delta_wheel_rad = models.FloatField(null=True)
	timestamp = models.FloatField(null=True)
	gas = models.FloatField(null=True)
	brake = models.FloatField(null=True)
	clutch = models.FloatField(null=True)
	gear = models.FloatField(null=True)
	rpm = models.FloatField(null=True)
	front_brake_pressure = models.FloatField(null=True)
	rear_brake_pressure = models.FloatField(null=True)
	vehicle_timestamp = models.FloatField(null=True)
	cba_actual_pressure_fl_pa = models.FloatField(null=True)
	cba_actual_pressure_fr_pa = models.FloatField(null=True)
	cba_actual_pressure_rl_pa = models.FloatField(null=True)
	cba_actual_pressure_rr_pa = models.FloatField(null=True)

	class Meta:
		db_table = "topic_state_estimation"


class TopicTfTransform(models.Model):
	id = models.BigAutoField(primary_key=True)
	record = models.ForeignKey(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		db_column="record_id",
		related_name="topic_tf_transforms",
	)
	transform_index = models.IntegerField()
	parent_frame_id = models.TextField()
	child_frame_id = models.TextField()
	stamp_ns = models.BigIntegerField()
	translation_x = models.FloatField(null=True)
	translation_y = models.FloatField(null=True)
	translation_z = models.FloatField(null=True)
	rotation_x = models.FloatField(null=True)
	rotation_y = models.FloatField(null=True)
	rotation_z = models.FloatField(null=True)
	rotation_w = models.FloatField(null=True)

	class Meta:
		db_table = "topic_tf_transform"
		constraints = [
			models.UniqueConstraint(
				fields=["record", "transform_index"],
				name="uq_tf_record_transform_index",
			)
		]
		indexes = [
			models.Index(fields=["parent_frame_id", "child_frame_id"], name="ix_tf_parent_child"),
			models.Index(fields=["stamp_ns"], name="ix_tf_stamp_ns"),
		]


class TopicCbaStatusFl(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_cba_status_fl",
	)
	cba_actual_pressure_fl_pa = models.FloatField(null=True)
	cba_actual_pressure_fl = models.FloatField(null=True)
	cba_target_pressure_fl_ack = models.FloatField(null=True)
	cba_actual_current_fl_a = models.FloatField(null=True)
	cba_voltage_fl_v = models.FloatField(null=True)

	class Meta:
		db_table = "topic_cba_status_fl"


class TopicCbaStatusFr(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_cba_status_fr",
	)
	cba_actual_pressure_fr_pa = models.FloatField(null=True)
	cba_actual_pressure_fr = models.FloatField(null=True)
	cba_target_pressure_fr_ack = models.FloatField(null=True)
	cba_actual_current_fr_a = models.FloatField(null=True)
	cba_voltage_fr_v = models.FloatField(null=True)

	class Meta:
		db_table = "topic_cba_status_fr"


class TopicCbaStatusRl(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_cba_status_rl",
	)
	cba_actual_pressure_rl_pa = models.FloatField(null=True)
	cba_actual_pressure_rl = models.FloatField(null=True)
	cba_target_pressure_rl_ack = models.FloatField(null=True)
	cba_actual_current_rl_a = models.FloatField(null=True)
	cba_voltage_rl_v = models.FloatField(null=True)

	class Meta:
		db_table = "topic_cba_status_rl"


class TopicCbaStatusRr(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_cba_status_rr",
	)
	cba_actual_pressure_rr_pa = models.FloatField(null=True)
	cba_actual_pressure_rr = models.FloatField(null=True)
	cba_target_pressure_rr_ack = models.FloatField(null=True)
	cba_actual_current_rr_a = models.FloatField(null=True)
	cba_voltage_rr_v = models.FloatField(null=True)

	class Meta:
		db_table = "topic_cba_status_rr"


class TopicHlMsg01(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_hl_msg_01",
	)
	hl_alive_01 = models.SmallIntegerField(null=True)
	hl_target_pressure_rr = models.FloatField(null=True)
	hl_target_pressure_rl = models.FloatField(null=True)
	hl_target_pressure_fr = models.FloatField(null=True)
	hl_target_pressure_fl = models.FloatField(null=True)
	hl_target_gear = models.SmallIntegerField(null=True)
	hl_target_throttle = models.FloatField(null=True)

	class Meta:
		db_table = "topic_hl_msg_01"


class TopicHlMsg02(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_hl_msg_02",
	)
	hl_alive_02 = models.SmallIntegerField(null=True)
	hl_psa_mode_of_operation = models.SmallIntegerField(null=True)
	hl_target_psa_control = models.FloatField(null=True)
	hl_psa_profile_acc_rad_s2 = models.IntegerField(null=True)
	hl_psa_profile_dec_rad_s2 = models.IntegerField(null=True)
	hl_psa_profile_vel_rad_s = models.IntegerField(null=True)

	class Meta:
		db_table = "topic_hl_msg_02"


class TopicPsaStatus01(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_psa_status_01",
	)
	psa_actual_pos_rad = models.FloatField(null=True)
	psa_actual_speed_rad_s = models.FloatField(null=True)
	psa_actual_torque_m_nm = models.FloatField(null=True)
	psa_actual_mode_of_operation = models.SmallIntegerField(null=True)
	psa_actual_current_a = models.FloatField(null=True)
	psa_actual_voltage_v = models.FloatField(null=True)

	class Meta:
		db_table = "topic_psa_status_01"


class TopicPsaStatus02(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_psa_status_02",
	)
	psa_target_psa_control_ack = models.FloatField(null=True)
	psa_actual_pos = models.FloatField(null=True)
	psa_actual_speed = models.FloatField(null=True)
	psa_actual_torque = models.FloatField(null=True)

	class Meta:
		db_table = "topic_psa_status_02"


class TopicWheelsSpeed01(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_wheels_speed_01",
	)
	wss_speed_fl_rad_s = models.FloatField(null=True)
	wss_speed_fr_rad_s = models.FloatField(null=True)
	wss_speed_rl_rad_s = models.FloatField(null=True)
	wss_speed_rr_rad_s = models.FloatField(null=True)

	class Meta:
		db_table = "topic_wheels_speed_01"


class TopicKistlerAccBody(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_kistler_acc_body",
	)
	acc_x_body = models.FloatField(null=True)
	acc_y_body = models.FloatField(null=True)
	acc_z_body = models.FloatField(null=True)

	class Meta:
		db_table = "topic_kistler_acc_body"


class TopicKistlerAngVelBody(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_kistler_ang_vel_body",
	)
	ang_vel_x_body = models.FloatField(null=True)
	ang_vel_y_body = models.FloatField(null=True)
	ang_vel_z_body = models.FloatField(null=True)

	class Meta:
		db_table = "topic_kistler_ang_vel_body"


class TopicKistlerCorrevit(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_kistler_correvit",
	)
	vel_x_cor = models.FloatField(null=True)
	vel_y_cor = models.FloatField(null=True)
	vel_cor = models.FloatField(null=True)
	angle_cor = models.FloatField(null=True)

	class Meta:
		db_table = "topic_kistler_correvit"


class TopicIceStatus01(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_ice_status_01",
	)
	ice_actual_gear = models.FloatField(null=True)
	ice_target_gear_ack = models.FloatField(null=True)
	ice_actual_throttle = models.FloatField(null=True)
	ice_target_throttle_ack = models.FloatField(null=True)
	ice_push_to_pass_req = models.FloatField(null=True)
	ice_push_to_pass_ack = models.FloatField(null=True)
	ice_water_press_k_pa = models.FloatField(null=True)
	ice_available_fuel_l = models.FloatField(null=True)
	ice_downshift_available = models.FloatField(null=True)

	class Meta:
		db_table = "topic_ice_status_01"


class TopicIceStatus02(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_ice_status_02",
	)
	ice_oil_temp_deg_c = models.FloatField(null=True)
	ice_engine_speed_rpm = models.FloatField(null=True)
	ice_fuel_press_k_pa = models.FloatField(null=True)
	ice_water_temp_deg_c = models.FloatField(null=True)
	ice_oil_press_k_pa = models.FloatField(null=True)

	class Meta:
		db_table = "topic_ice_status_02"


class TopicBadenia560TpmsFront(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_badenia_560_tpms_front",
	)
	tpr4_temp_fl = models.FloatField(null=True)
	tpr4_temp_fr = models.FloatField(null=True)
	tpr4_abs_press_fr = models.FloatField(null=True)
	tpr4_abs_press_fl = models.FloatField(null=True)

	class Meta:
		db_table = "topic_badenia_560_tpms_front"


class TopicBadenia560TpmsRear(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_badenia_560_tpms_rear",
	)
	tpr4_temp_rl = models.FloatField(null=True)
	tpr4_temp_rr = models.FloatField(null=True)
	tpr4_abs_press_rl = models.FloatField(null=True)
	tpr4_abs_press_rr = models.FloatField(null=True)

	class Meta:
		db_table = "topic_badenia_560_tpms_rear"


class TopicBadenia560TyreSurfaceTempFront(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_badenia_560_tyre_surface_temp_front",
	)
	outer_fl = models.FloatField(null=True)
	center_fl = models.FloatField(null=True)
	inner_fl = models.FloatField(null=True)
	outer_fr = models.FloatField(null=True)
	center_fr = models.FloatField(null=True)
	inner_fr = models.FloatField(null=True)

	class Meta:
		db_table = "topic_badenia_560_tyre_surface_temp_front"


class TopicBadenia560TyreSurfaceTempRear(models.Model):
	record = models.OneToOneField(
		TelemetryIdentity,
		on_delete=models.CASCADE,
		primary_key=True,
		db_column="record_id",
		related_name="topic_badenia_560_tyre_surface_temp_rear",
	)
	outer_rl = models.FloatField(null=True)
	center_rl = models.FloatField(null=True)
	inner_rl = models.FloatField(null=True)
	outer_rr = models.FloatField(null=True)
	center_rr = models.FloatField(null=True)
	inner_rr = models.FloatField(null=True)

	class Meta:
		db_table = "topic_badenia_560_tyre_surface_temp_rear"


class CameraFrame(models.Model):
	"""Metadata for camera frame images from onboard cameras."""
	race_id = models.TextField()
	camera = models.IntegerField()  # 0 = front-left, 1 = rear
	frame_number = models.IntegerField()  # Sequential frame index for the camera/race
	timestamp_seconds = models.FloatField()  # Lap-relative timestamp in seconds (e.g., 8.4 = 0:08.4)
	fps = models.IntegerField()  # Capture rate: 5 or 10 Hz
	file_path = models.TextField()  # Relative path to image file (e.g., "frames/r12/cam0/frame_0042.jpg")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		db_table = "camera_frame"
		constraints = [
			models.UniqueConstraint(
				fields=["race_id", "camera", "frame_number"],
				name="uq_camera_frame_race_camera_frame_number",
			)
		]
		indexes = [
			models.Index(fields=["race_id", "camera"], name="ix_camera_frame_race_camera"),
			models.Index(fields=["race_id", "camera", "timestamp_seconds"], name="ix_camera_frame_race_camera_ts"),
		]


class CameraFrameSQLiteBlob(models.Model):
	"""SQLite-oriented storage for full camera images and aligned position data."""
	race_id = models.TextField()
	camera = models.IntegerField()  # 0 = front-left, 1 = rear
	frame_number = models.IntegerField()
	timestamp_seconds = models.FloatField()
	timestamp_ns = models.BigIntegerField()
	x_m = models.FloatField(null=True)
	y_m = models.FloatField(null=True)
	z_m = models.FloatField(null=True)
	telemetry_race_id = models.TextField(null=True)
	telemetry_ts_ns = models.BigIntegerField(null=True)
	file_path = models.TextField()
	image_format = models.CharField(max_length=16, default="jpg")
	image_size_bytes = models.IntegerField()
	image_blob = models.BinaryField()
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = "camera_frame_sqlite_blob"
		constraints = [
			models.UniqueConstraint(
				fields=["race_id", "camera", "frame_number"],
				name="uq_cam_blob_race_cam_frame",
			)
		]
		indexes = [
			models.Index(fields=["race_id", "camera"], name="ix_cam_blob_race_cam"),
			models.Index(fields=["race_id", "camera", "timestamp_ns"], name="ix_cam_blob_race_cam_tsns"),
		]
