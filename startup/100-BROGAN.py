file_loading_timer.start()

from time import monotonic,sleep
import epics

DEBUG = True

Q_INTERVAL = 1  # Query interval for PID and temp setting
GIVE_UP = 10*60   # After this many seconds proceed with data collectoin even if perfect temp has not been acheived
MIN_FLAT_CNTS = 3 * 60 / Q_INTERVAL    # Min number of seconds a curve needs to be flat to move on

sample_temp = epics.PV("XF:28ID1-ES{LS336:1-Chan:C}T-I")
lakeshore_out = epics.PV("XF:28ID1-ES{LS336:1-Out:1}T-SP")
range_pv = epics.PV("XF:28ID1-ES{LS336:1-Out:1}Val:Range-Sel")
ramp_pv = epics.PV("XF:28ID1-ES{LS336:1-Out:1}Val:Ramp-SP")
p_gain_pv = epics.PV("XF:28ID1-ES{LS336:1-Out:1}Gain:P-SP")
i_gain_pv = epics.PV("XF:28ID1-ES{LS336:1-Out:1}Gain:I-SP")
d_gain_pv = epics.PV("XF:28ID1-ES{LS336:1-Out:1}Gain:D-SP")

def _debug(statement):
    if DEBUG:
        print(statement)

def _sanity_check(t_list: list)->bool:
    """Return True if temperature list is insane"""
    return any(x > 500 for x in t_list)

def _set_ramp(ramp_rate:float) -> float:
    ramp_pv.put(ramp_rate)
    return ramp_rate # Degrees K per second

def _setPIDs(target_temp:float, t_diff:float, cooling:bool):
    """
    Set PID parameters of device based on target temperature

    Args:
        target_temp (float): Temp to be sent to lakshore 
        direction (bool):  If true unit is cooling

    Returns:
        min_complete_seconds (float): an estimate of min delta T in Kelvin/second
    """

    # Anything over 300K needs to be in 5K steps
    
    t_change_rate = _set_ramp(6)

    if not cooling:
        
        """With the lower ramp rate we should be able to increase PI of >270 maybe 35 & 8"""
        if target_temp >= 410:
            if t_diff > 5:
                # t_change_rate = _set_ramp(2)
                pass
            elif t_diff <= 5:
                pass
                # t_change_rate = _set_ramp(4)
            p_gain_pv.put(35)
            i_gain_pv.put(8)
            d_gain_pv.put(2)

        elif target_temp >= 300:
            if t_diff > 5:
                pass
                # t_change_rate = _set_ramp(2)
            elif t_diff <= 5:
                pass
                # t_change_rate = _set_ramp(6)

        elif target_temp >= 270:
            # range_pv.put(3)
            # lowest_ramp_rate = .015 # K/s
            # t_change_rate = _set_ramp(6)
            p_gain_pv.put(26)
            i_gain_pv.put(5)
            d_gain_pv.put(3)

        elif target_temp >= 140:
            # range_pv.put(3)
            # lowest_ramp_rate = .02 # K/s
            # t_change_rate = _set_ramp(8)
            p_gain_pv.put(25)
            i_gain_pv.put(6)
            d_gain_pv.put(3)

        elif target_temp < 140:
            # range_pv.put(2)
            # lowest_ramp_rate = .04 # K/s
            # t_change_rate = _set_ramp(8)
            p_gain_pv.put(50)
            i_gain_pv.put(10)
            d_gain_pv.put(1)

    
    elif cooling:
        # t_change_rate = _set_ramp(8)

        if target_temp < 140:
            # range_pv.put(2)
            # lowest_ramp_rate = .04 # K/s
            p_gain_pv.put(25)
            i_gain_pv.put(4)
            d_gain_pv.put(3)

        elif target_temp > 200:
            # range_pv.put(3)
            # lowest_ramp_rate = .015 # K/s
            p_gain_pv.put(35)
            i_gain_pv.put(8)
            d_gain_pv.put(3)

        elif target_temp > 140:
            # range_pv.put(3)
            # lowest_ramp_rate = .02 # K/s
            p_gain_pv.put(25)
            i_gain_pv.put(6)
            d_gain_pv.put(3)

    return (abs(t_diff) / t_change_rate) * 60

def _detect_target_reached(targ,actual):
    if targ + .5 > actual and targ -.5 < actual:
        _debug("Target Reached")
        return 1
    else:
        return 0

def _detect_flat(data):
    d_len = len(data)

    if d_len < MIN_FLAT_CNTS:
        return 0
    
    if max(data) - min(data) < 2:
        # _debug("Its flat")
        return 1
    return 0

def change_T(target_temp:float): # Cryostat chanel A setpoint loop
    
    last_x_mins = []
    start_time = monotonic()
    flat_curve = False
    temp_reached = False

    curr_temp = float(sample_temp.get())
    lakeshore_out.put(target_temp)

    # Determin temp diff and direction 
    t_diff = curr_temp - target_temp
    if t_diff > 1:
        cooling = True
    else:
        cooling = False

    minseconds = _setPIDs(target_temp,t_diff,cooling)

    _debug(f"Attempting to reach {target_temp}K giving up after {GIVE_UP + minseconds} seconds")

    while not flat_curve or not temp_reached: # At somepoint we must move on
        t_now = monotonic()

        curr_temp = float(sample_temp.get())
        
        last_x_mins.append(curr_temp)
        if len(last_x_mins) > MIN_FLAT_CNTS:
            last_x_mins.pop(0)

        # Temp needs to be reached but flat may not happen at target temp
        # Once temp is reached latch
        if not temp_reached:
            temp_reached = _detect_target_reached(target_temp,curr_temp)

        flat_curve = _detect_flat(last_x_mins)
        
        # Check the range setting if things are taking too long
        if t_now - start_time > (3 * 60) and not temp_reached:

            curr_range = int(range_pv.get())
            if curr_range < 3 and not cooling:
                _debug(f"Raising range\n")
                range_pv.put(curr_range + 1)

            # if curr_range > 1 and cooling:
            #     _debug(f"Lowering range\n")
            #     range_pv.put(curr_range - 1)

        # Give up if taking too long
        if t_now - start_time > (GIVE_UP + minseconds):
            break

        sleep(Q_INTERVAL)

file_loading_timer.stop()
