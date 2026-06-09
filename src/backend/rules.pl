% ==============================================================================
%  F1 COGNITIVE TELEMETRY STREAM - KNOWLEDGE BASE (MASTER)
%  Neuro-Symbolic Logic Engine for Race Strategy & Physics Analysis
% ==============================================================================

% --- DYNAMIC FACTS (Asserted by Python Backend) ---
% current_tire(Driver, Compound, AgeLaps).
% tire_temp(Driver, SurfaceTemp).
% tire_wear(Driver, PercentageUsed).
% track_temp(Degrees).
% weather_intensity(RainLevel).  % 0=Dry, 1-3=Drizzle, 4-7=Rain, 8+=Storm
% gap_to_driver(Me, Rival, Seconds). (+ means I am behind, - means I am ahead)
% lap_time(Driver, Seconds).
% position(Driver, Pos).
% laps_remaining(Count).
% track_status(Status).          % 1=Green, 2=Yellow, 4=SC, 6=VSC
% pit_loss_time(Seconds).        % Time lost in pit lane (e.g., 22.0)
% traffic_at_pit_exit(Boolean).  % true if pit window exit index is crowded
% drs_enabled(ZoneID).
% speed_trap(Driver, Kph).
% interval_to_leader(Driver, Seconds).
% teammate_of(Driver, Teammate).
% is_engine_hot(Driver).
% rain_forecast(Minutes, Intensity).
% track_grip_level(Percentage).
% wind_speed(Kph).
% wind_direction(Degree).

% --- STATIC KNOWLEDGE (Physics Constants) ---

% 1. Optimal Temperature Windows
optimal_window(soft, 90, 110).
optimal_window(medium, 95, 115).
optimal_window(hard, 100, 120).
optimal_window(intermediate, 70, 90).
optimal_window(wet, 50, 70).

% 2. Graining Phases
graining_window(soft, 3, 8).
graining_window(medium, 6, 12).
graining_window(hard, 10, 18).

% 3. Life Expectancy (The Cliff)
tire_life_limit(soft, 15).
tire_life_limit(medium, 25).
tire_life_limit(hard, 40).
tire_life_limit(intermediate, 20).
tire_life_limit(wet, 18).

% 4. Strategy Constants
fresh_tire_advantage(1.5).
dry_pole_time(90.0). % Example reference time

% ==============================================================================
%  MODULE 1: TIRE PHYSICS & COMPOUND DYNAMICS (Rules 1-15)
% ==============================================================================

% RULE 1: THERMAL DEGRADATION CHECK
is_overheating(Driver, TempDiff) :-
    current_tire(Driver, Compound, _),
    tire_temp(Driver, CurrentTemp),
    optimal_window(Compound, _, MaxTemp),
    CurrentTemp > MaxTemp,
    TempDiff is CurrentTemp - MaxTemp.

% RULE 2: COLD TIRE GRIP LOSS
is_too_cold(Driver) :-
    current_tire(Driver, Compound, _),
    tire_temp(Driver, CurrentTemp),
    optimal_window(Compound, MinTemp, _),
    CurrentTemp < MinTemp.

% RULE 3: GRAINING PHASE DETECTION
is_graining(Driver) :-
    current_tire(Driver, Compound, Age),
    graining_window(Compound, Start, End),
    Age >= Start,
    Age =< End.

% RULE 4: THE "CLIFF" (PERFORMANCE DROP)
hit_the_cliff(Driver) :-
    current_tire(Driver, Compound, Age),
    tire_life_limit(Compound, Limit),
    Age > Limit.

% RULE 5: CRITICAL WEAR WARNING
puncture_risk_high(Driver) :-
    tire_wear(Driver, Wear),
    Wear > 85.

% RULE 6: COMPOUND-TRACK MISMATCH (HARD)
compound_mismatch(Driver) :-
    current_tire(Driver, hard, _),
    track_temp(T),
    T < 25.

% RULE 7: COMPOUND-TRACK MISMATCH (SOFT)
compound_mismatch(Driver) :-
    current_tire(Driver, soft, _),
    track_temp(T),
    T > 45.

% RULE 8: CROSSOVER POINT (SLICK TO INTER)
recommend_inter(Driver) :-
    current_tire(Driver, slick, _),
    weather_intensity(Rain),
    Rain > 1, Rain < 5.

% RULE 9: CROSSOVER POINT (INTER TO WET)
recommend_wet(Driver) :-
    current_tire(Driver, inter, _),
    weather_intensity(Rain),
    Rain >= 5.

% RULE 10: DRY LINE LOGIC (WRONG TIRE)
wrong_tire_for_dry(Driver) :-
    weather_intensity(0),
    (current_tire(Driver, intermediate, _); current_tire(Driver, wet, _)).

% RULE 11: WARM-UP STRUGGLE
warmup_critical(Driver) :-
    is_too_cold(Driver),
    track_temp(T),
    T < 30.

% RULE 12: BLISTERING RISK
blistering_risk(Driver) :-
    is_overheating(Driver, _),
    tire_wear(Driver, Wear),
    Wear > 60.

% RULE 13: UNDERCUT DEFENSE (TIRE DELTA)
vulnerable_to_undercut(Driver, Rival) :-
    current_tire(Driver, _, MyAge),
    current_tire(Rival, _, RivalAge),
    MyAge > 15,
    RivalAge < 5.

% RULE 14: AGGREGATE TIRE DIAGNOSIS (CRITICAL)
get_tire_diagnosis(Driver, Status, Reason) :-
    puncture_risk_high(Driver),
    Status = 'CRITICAL', Reason = 'STRUCTURAL INTEGRITY FAILING'.
get_tire_diagnosis(Driver, Status, Reason) :-
    hit_the_cliff(Driver),
    Status = 'CRITICAL', Reason = 'PERFORMANCE CLIFF REACHED'.
get_tire_diagnosis(Driver, Status, Reason) :-
    blistering_risk(Driver),
    Status = 'WARNING', Reason = 'BLISTERING DETECTED'.
get_tire_diagnosis(Driver, Status, Reason) :-
    is_graining(Driver),
    Status = 'CAUTION', Reason = 'GRAINING PHASE'.
get_tire_diagnosis(Driver, Status, Reason) :-
    is_overheating(Driver, Diff),
    Status = 'CAUTION', Reason = 'OVERHEATING', Diff > 5.

% RULE 15: AGGREGATE TIRE DIAGNOSIS (OPTIMAL)
get_tire_diagnosis(Driver, Status, Reason) :-
    \+ puncture_risk_high(Driver),
    \+ hit_the_cliff(Driver),
    \+ blistering_risk(Driver),
    \+ is_graining(Driver),
    Status = 'OPTIMAL', Reason = 'TIRES IN OPERATING WINDOW'.

% ==============================================================================
%  MODULE 2: RACE STRATEGY & PIT STOPS (Rules 16-27)
% ==============================================================================

% RULE 16: UNDERCUT DETECTION
recommend_undercut(Me, Rival) :-
    gap_to_driver(Me, Rival, Gap),
    Gap > 0, Gap < 1.5,
    track_status(1),
    \+ traffic_at_pit_exit(true).

% RULE 17: OVERCUT DEFENSE
must_cover_rival(Me, Rival) :-
    gap_to_driver(Me, Rival, Gap),
    Gap < 0, Gap > -2.0,
    rival_action(Rival, 'IN_PIT').

% RULE 18: CHEAP PIT STOP (SAFETY CAR)
cheap_pit_opportunity(Me) :-
    (track_status(4); track_status(6)),
    current_tire(Me, _, Age),
    Age > 10.

% RULE 19: PIT WINDOW BLOCKED
pit_window_closed(Me) :-
    traffic_at_pit_exit(true).

% RULE 20: LATE RACE SOFT GAMBLE
gamble_softs(Me) :-
    laps_remaining(Laps), Laps < 5,
    position(Me, Pos), Pos > 10,
    gap_to_driver(Me, _, GapBehind),
    pit_loss_time(Loss),
    GapBehind > Loss.

% RULE 21: EXTEND STINT (ONE-STOPPER)
suggest_extend_stint(Me) :-
    get_tire_diagnosis(Me, 'OPTIMAL', _),
    laps_remaining(Laps),
    current_tire(Me, hard, _),
    Laps < 15.

% RULE 22: FORCED PIT (COMPOUND RULE)
mandatory_pit_alert(Me) :-
    laps_remaining(1),
    used_compounds(Me, CompoundsList),
    length(CompoundsList, 1).

% RULE 23: RAIN SURVIVAL MODE
emergency_box_wets(Me) :-
    current_tire(Me, slick, _),
    weather_intensity(Rain), Rain > 7.

% RULE 24: DRY TRACK SLICK TRANSITION
box_for_slicks(Me) :-
    current_tire(Me, intermediate, _),
    track_status(1),
    lap_time(Me, MyTime),
    lap_time(fastest_slick_runner, RefTime),
    MyTime > (RefTime + 2.0).

% RULE 25: DOUBLE STACK WARNING
avoid_double_stack(Me, Teammate) :-
    teammate_of(Me, Teammate),
    rival_action(Teammate, 'IN_PIT'),
    gap_to_driver(Me, Teammate, Gap),
    Gap < 3.0.

% RULE 26: TO THE END
can_finish_race(Me) :-
    laps_remaining(Laps),
    current_tire(Me, Compound, Age),
    tire_life_limit(Compound, Limit),
    (Age + Laps) < Limit.

% RULE 27: FIGHT FOR POSITION
engine_mode_push(Me) :-
    laps_remaining(Laps), Laps < 3,
    gap_to_driver(Me, _, Gap),
    Gap < 1.0, Gap > -1.0.

% ==============================================================================
%  MODULE 3: RACE CRAFT & OVERTAKING (Rules 28-38)
% ==============================================================================

% RULE 28: DRS ATTACK MODE
drs_attack_active(Me, Rival) :-
    gap_to_driver(Me, Rival, Gap),
    Gap > 0, Gap < 1.0,
    drs_enabled(_).

% RULE 29: CRITICAL DEFENSE
initiate_defense_mode(Me) :-
    gap_to_driver(Me, _, GapBehind),
    GapBehind < 0.7, GapBehind > -0.1,
    \+ is_blue_flag(Me).

% RULE 30: BLUE FLAG YIELD
blue_flag_warning(Me) :-
    interval_to_leader(Me, GapLeader),
    GapLeader > 1.5,
    track_status(1).

% RULE 31: DIRTY AIR MANAGEMENT
dirty_air_critical(Me) :-
    gap_to_driver(Me, _, Gap),
    Gap > 0, Gap < 2.0,
    is_engine_hot(Me).

% RULE 32: TEAM ORDER (SWITCH)
team_order_switch(Me, Teammate) :-
    teammate_of(Me, Teammate),
    gap_to_driver(Me, Teammate, Gap),
    Gap < 1.0,
    get_tire_diagnosis(Teammate, 'OPTIMAL', _),
    get_tire_diagnosis(Me, 'CAUTION', _).

% RULE 33: LIFT AND COAST
lift_and_coast_suggested(Me) :-
    (is_engine_hot(Me); fuel_status(Me, 'LOW')),
    gap_to_driver(Me, _, GapBehind),
    GapBehind > 3.0.

% RULE 34: OVERTAKE PROBABILITY HIGH
high_overtake_chance(Me, Rival) :-
    drs_attack_active(Me, Rival),
    current_tire(Me, soft, AgeMe),
    current_tire(Rival, hard, AgeRival),
    AgeMe < 5, AgeRival > 15.

% RULE 35: FREE AIR PUSH
free_air_push(Me) :-
    gap_to_driver(Me, Rival, Gap),
    Gap > 5.0,
    get_tire_diagnosis(Me, 'OPTIMAL', _).

% RULE 36: ERS CHARGING LAP
recharge_battery(Me) :-
    ers_level(Me, Level), Level < 20,
    gap_to_driver(Me, _, GapBehind),
    GapBehind > 2.0.

% RULE 37: SAFETY CAR RESTART PREP
prepare_restart(Me) :-
    track_status(4),
    sc_in_this_lap(true),
    is_too_cold(Me).

% RULE 38: BREAK TOW
break_drs_tow(Me) :-
    gap_to_driver(Me, _, GapBehind),
    GapBehind > 0.8, GapBehind < 1.1,
    ers_level(Me, Level), Level > 50.

% ==============================================================================
%  MODULE 4: WEATHER & ENVIRONMENTAL PHYSICS (Rules 39-50)
% ==============================================================================

% RULE 39: RAIN IMMINENT (STAY OUT)
hold_for_rain(Me) :-
    rain_forecast(Mins, Intensity),
    Mins < 4, Intensity > 2,
    current_tire(Me, slick, _).

% RULE 40: TRACK EVOLUTION (RAMP UP)
track_evolving_fast() :-
    track_grip_level(Grip), Grip < 80,
    weather_intensity(0).

% RULE 41: SLICK-TO-INTER CROSSOVER (REFINED)
crossover_slick_to_inter(Me) :-
    current_tire(Me, slick, _),
    lap_time(Me, CurrentTime),
    dry_pole_time(Pole),
    Ratio is CurrentTime / Pole,
    Ratio > 1.15.

% RULE 42: INTER-TO-WET CROSSOVER
crossover_inter_to_wet(Me) :-
    current_tire(Me, intermediate, _),
    rain_forecast(0, Intensity),
    Intensity > 8.

% RULE 43: GAMBLE ON SLICKS (DRYING TRACK)
gamble_early_slicks(Me) :-
    current_tire(Me, intermediate, _),
    weather_intensity(0),
    track_temp(T), T > 30.

% RULE 44: HEADWIND BRAKING
brake_later_t1() :-
    wind_speed(Speed), Speed > 15,
    wind_direction(Dir), Dir > 170, Dir < 190.

% RULE 45: TAILWIND INSTABILITY
caution_tailwind_turn(TurnID) :-
    wind_speed(Speed), Speed > 20,
    wind_direction(Dir),
    turn_orientation(TurnID, Dir).

% RULE 46: VISIBILITY CRITICAL
increase_safety_gap(Me) :-
    weather_intensity(Rain), Rain > 5,
    gap_to_driver(Me, Rival, Gap),
    Gap < 2.0.

% RULE 47: TIRE WARMUP IN WET
keep_wets_warm(Me) :-
    current_tire(Me, wet, _),
    on_straight(Me),
    track_status(4).

% RULE 48: PUNCURE DEBRIS RISK
avoid_offline_curbs() :-
    track_report('DEBRIS').

% RULE 49: RED FLAG RESTART TIRE
red_flag_strategy(Me) :-
    track_status(5),
    laps_remaining(L), L < 10.

% RULE 50: THE "PERFECT LAP" CONDITION
push_for_fastest_lap(Me) :-
    fuel_status(Me, 'LOW'),
    track_status(1),
    get_tire_diagnosis(Me, 'OPTIMAL', _),
    current_tire(Me, soft, _),
    gap_to_driver(Me, _, Gap), Gap > 3.0.

% ==============================================================================
%  MASTER QUERY: AI RACE ENGINEER
%  Python calls this to get the single most important message.
% ==============================================================================

get_engineer_message(Driver, Msg) :-
    puncture_risk_high(Driver), Msg = 'BOX NOW - PUNCTURE RISK'.
get_engineer_message(Driver, Msg) :-
    emergency_box_wets(Driver), Msg = 'BOX NOW - HEAVY RAIN'.
get_engineer_message(Driver, Msg) :-
    recommend_undercut(Driver, Rival), atom_concat('BOX TO UNDERCUT ', Rival, Msg).
get_engineer_message(Driver, Msg) :-
    drs_attack_active(Driver, Rival), atom_concat('OVERTAKE BUTTON ON - ATTACK ', Rival, Msg).
get_engineer_message(Driver, Msg) :-
    blue_flag_warning(Driver), Msg = 'BLUE FLAGS - LET LEADER BY'.
get_engineer_message(Driver, Msg) :-
    hold_for_rain(Driver), Msg = 'STAY OUT - RAIN IMMINENT'.
get_engineer_message(Driver, Msg) :-
    dirty_air_critical(Driver), Msg = 'PULL BACK - ENGINE OVERHEATING'.
get_engineer_message(Driver, Msg) :-
    get_strategy_action(Driver, _, Reason), atom_concat('STRATEGY ALERT: ', Reason, Msg).
get_engineer_message(_, 'RADIO SILENCE'). % Default fallback