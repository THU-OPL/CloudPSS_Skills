# Parameters And Results

## Default Use

Use `run_disturbance_severity_analysis` with only:

- `cloudpss_model`
- Optional bus filters: `Keys`, `NameSet`, `VMin`, `VMax`

If no bus filters are provided, the tool automatically:

- inspects all bus `VBase` values in the model
- selects one real voltage level that exists in the model
- uses the voltage level with the largest bus count as the default monitored level
- prioritizes a small set of buses nearest to the faulted transmission component

This is the preferred path for non-expert users.

## Analysis Modes

- `quick`: smallest workload, preferred for default verification and fast user feedback
- `balanced`: moderate output size and slightly longer EMT horizon
- `detailed`: larger output size for users who explicitly ask for more detail

## Expert Parameters

### Performance And Scope

- `freq`: waveform sampling frequency
- `MaxCount`: max monitored bus count
- `emt_end_time`: EMT simulation horizon
- `n_cpu`, `n_ele_cpu`: CPU allocation

### Bus Scope

- `Keys`: explicit monitored bus keys, in priority order
- `NameSet`: explicit monitored bus names
- `VMin`, `VMax`: explicit voltage-level range filter

### DV Criteria

- `dv_judge`: custom voltage margin criteria
- `dv_vmin_recovery_ratio`: lower recovery bound
- `dv_vmax_recovery_ratio`: upper recovery bound

### SI Criteria

- `si_tinterval`: integration start offset after fault
- `si_window`: first-stage integration window length
- `si_stage1_threshold`: stage-1 deviation threshold
- `si_stage2_threshold`: stage-2 deviation threshold

## Returned Results

- `severity_level`: heuristic severity label, one of `low`, `medium`, `high`, `severe`
- `analysis_conclusion`: concise natural-language summary for direct user display
- `bus_selection`: monitored-bus selection summary, including mode, selected voltage level, candidate count, selected buses, and available voltage levels
- `per_bus_summary`: per-bus structured summary including bus key, label, margins, validity, and violations
- `dv_result`: raw DV result payload
- `si_result`: raw SI result payload
- `dudv_plot`: saved DUDV plot path
- `artifacts.summary_json`: saved machine-readable summary
- `artifacts.summary_csv`: saved per-bus table
- `artifacts.summary_markdown`: saved human-readable report
- `artifacts.dv_margin_chart`: saved grouped bar chart of DV margins

## Interpretation Hints

- More negative DV upper or lower margins indicate stronger limit violations.
- Larger `SI` generally indicates more severe post-fault voltage recovery problems.
- `severity_level` is a heuristic summary; expert decisions should still inspect per-bus details and saved plots.
- In default mode, inspect `bus_selection` first to confirm the automatically chosen voltage level and monitored buses are reasonable for the case.