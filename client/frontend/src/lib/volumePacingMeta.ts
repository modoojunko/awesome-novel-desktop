/** 全书默认节奏的兜底键与段长（c-volume-pacing）。
 *  兜底与后端 volumes/pacing.py 的 DEFAULT_PRESET_KEY 同键；正文文案（六套路
 *  名称/步表/提示语）由 `/pacing/presets` 下发，前端不持第二份。 */
export const PACING_PRESET_DEFAULT_KEY = "upgrade";
export const PACING_STEPS_LEN_FALLBACK = 3;
