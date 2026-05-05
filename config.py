from typing import Any

class Config:
    """Plugin Config Here"""
    def __init__(self):
        # =========== 常规配置 ===========
        self.omtk_cache_max_age = 24
        self.max_file_size_mb = 50
        self.default_convert_od = 8
        self.default_convert_hp = 8
        
        # ... (rest of the fields)
        self.sim_right_cheat_threshold = 0.99
        self.sim_right_sus_threshold = 0.985
        self.sim_left_cheat_threshold = 0.4
        self.sim_left_sus_threshold = 0.55
        self.abnormal_peak_threshold = 0.33
        self.low_sample_rate_threshold = 165
        self.delta_chord_hard_min_count = 16
        self.delta_chord_hard_ratio = 0.82
        self.delta_chord_hard_p95 = 1.8
        self.delta_chord_soft_min_count = 8
        self.delta_chord_soft_ratio = 0.60
        self.delta_chord_soft_p90 = 2.2
        self.delta_dense_radius_ms = 180
        self.delta_dense_hard_mad = 1.8
        self.delta_dense_hard_ratio = 0.60
        self.delta_dense_soft_mad = 2.5
        self.delta_dense_soft_ratio = 0.70
        self.delta_gap_unmatched_ratio = 0.35
        self.delta_gap_press_ratio = 0.12
        self.delta_risk_cheat_score = 3
        self.delta_risk_sus_score = 1
        self.delta_col_autocorr_hard = 0.65
        self.delta_col_autocorr_soft = 0.50
        self.delta_col_lowfreq_hard = 0.48
        self.delta_col_lowfreq_soft = 0.38
        self.delta_chord_template_min_groups = 6
        self.delta_chord_template_quant_ms = 0.5
        self.delta_chord_template_span_ms = 1.4
        self.delta_chord_template_hard_ratio = 0.52
        self.delta_chord_template_hard_zero_ratio = 0.60
        self.delta_chord_template_soft_ratio = 0.38
        self.delta_chord_template_soft_zero_ratio = 0.50
        self.delta_gap_v2_min_gap_ms = 1000
        self.delta_gap_v2_inner_margin_ms = 100
        self.delta_gap_v2_ioi_quant_ms = 8.0
        self.delta_gap_v2_weight_unmatched = 0.30
        self.delta_gap_v2_weight_gap = 0.30
        self.delta_gap_v2_weight_regular = 0.30
        self.delta_gap_v2_weight_entropy = 0.10
        self.delta_gap_v2_soft_score = 0.45
        self.delta_gap_v2_hard_score = 0.60
        self.delta_gap_v2_weight_uniform = 0.10
        self.time_shape_smoothness_soft = 0.98
        self.time_shape_smoothness_hard = 0.99
        self.time_shape_smoothness_low = 0.86
        self.time_shape_fit_mse_soft = 0.030
        self.time_shape_fit_mse_hard = 0.022
        self.time_duration_freq_common_ratio = 0.9
        self.time_duration_freq_strength = 3.4
        self.delta_ar1_fit_soft_r2 = 0.95
        self.delta_ar1_fit_hard_r2 = 0.98
        self.delta_nonlinear_min_count = 260
        self.delta_nonlinear_bds_p = 0.01
        self.delta_nonlinear_bds_eps_scale = 0.7
        self.delta_nonlinear_pacf_threshold = 0.14
        self.delta_nonlinear_arch_p = 0.01
        self.delta_nonlinear_sqacf_threshold = 0.25
        self.delta_cross_corr_min_pairs = 100
        self.delta_cross_corr_threshold = 0.05
        self.delta_cross_corr_lag_threshold = 0.05
        self.delta_cross_corr_chord_tol_ms = 1.0
        self.delta_chord_near_zero_min_count = 20
        self.delta_chord_near_zero_ms = 0.25
        self.delta_chord_near_zero_soft_ratio = 0.72
        self.delta_chord_near_zero_hard_ratio = 0.82
        self.delta_chord_wide_ms = 2.0
        self.delta_chord_wide_soft_ratio = 0.10
        self.delta_chord_wide_hard_ratio = 0.06
        self.delta_fatigue_mono_soft = 0.83
        self.delta_fatigue_mono_hard = 0.9
        self.delta_fatigue_shape_diff_soft = 0.83
        self.delta_fatigue_shape_diff_hard = 0.9

        self.core_rating_multiplier = {
            "Stream": 1.0 / 3.0,
            "Chordstream": 0.65,
            "Jacks": 0.9,
            "Coordination": 0.75,
            "Density": 0.9,
            "Wildcard": 1.0,
        }

        self.subtype_rating_multiplier_by_mode = {
            "RC": {
                "Rolls": 1.0 / 3.0, "Trills": 1.0 / 3.0, "Minitrills": 1.0 / 3.0,
                "Handstream": 0.65, "Split Trill": 0.65, "Jumptrill": 0.65, "Jumpstream": 0.65,
                "Brackets": 0.65, "Double Stream": 0.65, "Dense Chordstream": 0.65, "Light Chordstream": 0.65, "Chord Rolls": 0.65,
                "Longjacks": 0.9, "Quadstream": 0.9, "Gluts": 0.9, "Chordjacks": 0.9, "Minijacks": 0.9,
                "Column Lock": 1.5, "Release": 0.73, "Shield": 0.8, "JS Density": 1.0, "HS Density": 1.0,
                "DS Density": 1.0, "LCS Density": 1.0, "DCS Density": 1.0, "Inverse": 1.3, "Jacky WC": 0.55, "Speedy WC": 0.8,
            },
            "LN": {
                "Rolls": 1.0 / 3.0, "Trills": 1.0 / 3.0, "Minitrills": 1.0 / 3.0,
                "Handstream": 0.65, "Split Trill": 0.65, "Jumptrill": 0.65, "Jumpstream": 0.65,
                "Brackets": 0.65, "Double Stream": 0.65, "Dense Chordstream": 0.65, "Light Chordstream": 0.65, "Chord Rolls": 0.65,
                "Longjacks": 0.9, "Quadstream": 0.9, "Gluts": 0.9, "Chordjacks": 0.9, "Minijacks": 0.9,
                "Column Lock": 1.5, "Release": 1.0, "Shield": 0.8, "JS Density": 0.9, "HS Density": 0.9,
                "DS Density": 0.9, "LCS Density": 0.9, "DCS Density": 0.9, "Inverse": 1.5, "Jacky WC": 0.55, "Speedy WC": 0.8,
            },
            "HB": {
                "Rolls": 1.0 / 3.0, "Trills": 1.0 / 3.0, "Minitrills": 1.0 / 3.0,
                "Handstream": 0.65, "Split Trill": 0.65, "Jumptrill": 0.65, "Jumpstream": 0.65,
                "Brackets": 0.65, "Double Stream": 0.65, "Dense Chordstream": 0.65, "Light Chordstream": 0.65, "Chord Rolls": 0.65,
                "Longjacks": 0.9, "Quadstream": 0.9, "Gluts": 0.9, "Chordjacks": 0.9, "Minijacks": 0.9,
                "Column Lock": 1.5, "Release": 0.3, "Shield": 0.8, "JS Density": 0.9, "HS Density": 0.9,
                "DS Density": 0.9, "LCS Density": 0.9, "DCS Density": 0.9, "Inverse": 0.0, "Jacky WC": 0.65, "Speedy WC": 0.45,
            },
            "Mix": {
                "Rolls": 1.0 / 3.0, "Trills": 1.0 / 3.0, "Minitrills": 1.0 / 3.0,
                "Handstream": 0.65, "Split Trill": 0.65, "Jumptrill": 0.65, "Jumpstream": 0.65,
                "Brackets": 0.65, "Double Stream": 0.65, "Dense Chordstream": 0.65, "Light Chordstream": 0.65, "Chord Rolls": 0.65,
                "Longjacks": 0.9, "Quadstream": 0.9, "Gluts": 0.9, "Chordjacks": 0.9, "Minijacks": 0.9,
                "Column Lock": 1.5, "Release": 0.3, "Shield": 0.8, "JS Density": 0.9, "HS Density": 0.9,
                "DS Density": 0.9, "LCS Density": 0.9, "DCS Density": 0.9, "Inverse": 0.0, "Jacky WC": 0.45, "Speedy WC": 0.45,
            },
        }

        self.rc_core_ln_scale = 0.3
        self.rc_ln_core_scale = 0.0
        self.release_with_dw_multiplier = 0.8
        self.ln_mode_low_threshold = 0.1
        self.ln_mode_high_threshold = 0.9
        self.hb_row_ratio_threshold = 0.1
        self.bpm_cluster_threshold = 5.0
        self.pattern_stability_threshold = 5.0
        self.important_cluster_ratio = 0.5
        self.category_js_hs_secondary_ratio = 0.4
        self.sv_amount_threshold = 2000.0
        self.sv_speed_eps = 0.05
        self.sv_extreme_bpm_min = 30.0
        self.sv_extreme_bpm_max = 350.0
        self.sv_extreme_bpm_ratio = 3.0
        self.cluster_specific_name_min_ratio = 0.0
        self.enable_multi_label_same_window = True
        self.coordination_specific_order = ["Column Lock", "Shield", "Release"]
        self.density_specific_order = ["Inverse", "JS Density", "HS Density", "DS Density", "DCS Density", "LCS Density"]
        self.wildcard_specific_order = ["Speedy WC", "Jacky WC"]
        self.jacks_min_bpm = 90.0
        self.shield_max_beat_ratio = 0.25
        self.inverse_gap_tolerance_ms = 5.0
        self.inverse_min_filled_lanes = 3
        self.release_scan_rows = 4
        self.release_min_tail_rows = 4
        self.release_roll_points = 2
        self.release_full_match_rows = 5
        self.jacky_context_window = 6
        self.jacky_fallback_max_mspb = 185.0

# 全局配置实例
_config_instance = Config()

def get_plugin_config(config_class=None):
    return _config_instance

def get_driver():
    class MockDriver:
        def on_startup(self, func):
            return func
    return MockDriver()