file_loading_timer.start()

import ophyd
from ophyd import (Device, Component as Cpt,
                   EpicsSignal, EpicsSignalRO, EpicsMotor)
from ophyd.areadetector import EpicsSignalWithRBV as SignalWithRBV, AreaDetector
from ophyd.status import SubscriptionStatus
import skimage

import bluesky.preprocessors as bpp
import bluesky.plan_stubs as bps
from bluesky.plans import count
from xpdacq.beamtime import _configure_area_det, close_shutter_stub, open_shutter_stub
from bluesky.utils import short_uid, MsgGenerator, plan

import datetime
import os

## disable live plots
bec.disable_plots()

def tqdm_sleep(rest_time, message='Sleep'):

    from tqdm import tqdm
    for j in tqdm(range(0,100), desc=message):
        time.sleep(rest_time/100)


def sleep_sec_q(t):
    import datetime
    from tqdm import tqdm
    now = datetime.datetime.now()
    print(f'Sleep for a while: {t} seconds.')
    print(f'Waiting starts at {now}')
    for i in tqdm(range(0,100), desc='Sleep'):
        yield from bps.sleep(t/100)



def auto_name_file(filename_prefix, file_extension, directory=None):
    """
    Generates a filename with the current date and time, and saves the file.

    Args:
        filename_prefix: The beginning of the fiEpicsSignallename (e.g., "data").
        file_extension: The file extension (e.g., ".txt", ".csv").
        directory: (Optional) The directory to save the file in.
                   If None, saves to the current working directory.

    Returns:
        The full path to the created file.
    """
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    if filename_prefix == '':
        new_filename = f"{timestamp}{file_extension}"
    else:
        new_filename = f"{filename_prefix}_{timestamp}{file_extension}"

    if directory:
        os.makedirs(directory, exist_ok=True)  # Create directory if it doesn't exist
        filepath = os.path.join(directory, new_filename)
    else:
        filepath = new_filename

    # Create an empty file (or overwrite if it exists)
    with open(filepath, 'w') as f:
        pass

    return filepath

# # Example usage:
# file_path = auto_name_file("my_data", ".txt", "my_files")
# print(f"File created at: {file_path}")

# file_path2 = auto_name_file("report", ".csv") # saves in current directory
# print(f"File created at: {file_path2}")


# shared by Milinda
def measurement_data(): # .......Captures metadata
    info_dict = {}
    info_dict['OT_stage_1_X'] = OT_stage_1_X.read()
    info_dict['OT_stage_1_Y'] = OT_stage_1_Y.read()
    info_dict['OT_stage_2_X'] = OT_stage_2_X.read()
    info_dict['OT_stage_2_Y'] = OT_stage_2_Y.read()
    info_dict['Det_1_X'] = Det_1_X.read()
    info_dict['Det_1_Y'] = Det_1_Y.read()
    info_dict['Det_1_Z'] = Det_1_Z.read()
    info_dict['Grid_X'] = Grid_X.read()
    info_dict['Grid_Y'] = Grid_Y.read()
    info_dict['Grid_Z'] = Grid_Z.read()
    info_dict['ring_current'] = ring_current.read()
    info_dict['frame_acq_time'] = glbl['frame_acq_time']
    info_dict['dk_window'] = glbl['dk_window']

    # info_dict['cryostat_A'] = lakeshore336.read()['lakeshore336_temp_A_T']['value']
    # info_dict['cryostat_A_V'] = caget('XF:28ID1-ES{LS336:1-Chan:A}Val:Sens-I')
    # info_dict['cryostat_B'] = lakeshore336.read()['lakeshore336_temp_B_T']['value']
    # info_dict['cryostat_B_V'] = caget('XF:28ID1-ES{LS336:1-Chan:B}Val:Sens-I')
    # info_dict['cryostat_C'] = lakeshore336.read()['lakeshore336_temp_C_T']['value']
    # info_dict['cryostat_C_V'] = caget('XF:28ID1-ES{LS336:1-Chan:C}Val:Sens-I')
    # info_dict['cryostat_D'] = lakeshore336.read()['lakeshore336_temp_D_T']['value']
    # info_dict['cryostat_D_V'] = caget('XF:28ID1-ES{LS336:1-Chan:D}Val:Sens-I')

    # info_dict['hotairblower'] = hotairblower.read()['hotairblower']['value']
    # info_dict['linkam_T96'] = linkam_T96.readback.get()
    # info_dict['cryostream_T'] = cs800.read()['temperature']['value']
    # info_dict['eurotherm3504'] = eurotherm3504.read()['eurotherm3504']['value']



    info_dict['Measurement_time'] = time.time()

    return info_dict


# from xpdacq.xpdacq import inject_metaddta

def _inject_pilatus_3pos(msg):
    """Inject the 3 positions of Pilstus in start.

        Tried on 2025/11/18 by CHL and doesn't work.
        msg.kwargs only goes into metadata when msg.command=='opend_run'.
    """
    # if msg.command == "open_run" and msg.kwargs.get("dark_frame") is not True:
    if msg.command == "create":
        print(f'\n{msg.command = }\n')
        x:dict = Grid_X.read()['Grid_X']
        y:dict = Grid_Y.read()['Grid_Y']
        print(f'\n{x = }\n')

        # x:dict = 22
        # y:dict = 12

        try:
            msg.kwargs["Pilatus_3pos_x"].append(x)
            msg.kwargs["Pilatus_3pos_x"].append(y)

        except KeyError:
            msg.kwargs["Pilatus_3pos_x"] = [x]
            msg.kwargs["Pilatus_3pos_y"] = [y]

        print(f'\n{msg.kwargs = }\n')

    else:
        print(f'\n{msg.command = }\n')
        print(f'\n{msg.kwargs = }\n')

    return msg



def pila_3pos(dets, exposure):
    """
    Take one reading from area detector with given exposure time

    Parameters
    ----------
    dets : list
        list of 'readable' objects. default to area detector
        linked to xpdAcq.
    exposure : float
        total time of exposrue in seconds

    Notes
    -----
    area detector being triggered will  always be the one configured
    in global state. To find out which these are, please using
    following commands:

        >>> xpd_configuration['area_det']

    to see which device is being linked
    """

    area_det = xpd_configuration["area_det"]

    (num_frame, acq_time, computed_exposure) = yield from _configure_area_det(exposure)

    # update md
    _md = ChainMap(
        {
            "sp_time_per_frame": acq_time,
            "sp_num_frames": num_frame,
            "sp_requested_exposure": exposure,
            "sp_computed_exposure": computed_exposure,
            "sp_type": "bps.trigger",
            "sp_uid": str(uuid.uuid4()),
            "sp_plan_name": "pila_3pos",
            "sp_detector": area_det.name,
            "detectors": [area_det.name],
        },
    )

    #det_x_pos = [40.644, 31.356, 36] - MA detector mounting is different 07/04/2025
    det_x_pos = [20.644, 11.356, 16]
    det_y_pos = [-3.356, -12.644, -8]

    motors = [Grid_X, Grid_Y, Grid_Z]

    @bpp.stage_decorator([area_det]+motors)
    @bpp.run_decorator(md=_md)
    def pdf_RE_inner(area_det, det_x_pos=det_x_pos, det_y_pos=det_y_pos):
        # _md = {'detectors':[det.name]}
        # _md.update(md or {})

        def trigger_det(stream_name):
            ret = {}
            yield from bps.trigger(area_det, wait=True)
            yield from bps.create(name=stream_name)
            # reading = (yield from bps.read(area_det))
            # print(f"reading = {reading}")
            # ret.update(reading)
            yield from bps.read(area_det)
            yield from bps.read(Grid_X)
            yield from bps.read(Grid_Y)
            yield from bps.save()

        if 'pe1' in area_det.name:
            yield from periodic_dark(trigger_det(f"{area_det.name}_00"))

        elif 'pilatus' in area_det.name:
            for i in range(len(det_x_pos)):
                yield from bps.mv(fs, 1)
                print(f'Open shutter for Pilatus position {i}')
                yield from bps.mv(Grid_X, det_x_pos[i], Grid_Y, det_y_pos[i])
                yield from periodic_dark(trigger_det(f"{area_det.name}_pos{i}"))
                yield from bps.mv(fs, 0)
                print(f'Finish Pilatus position {i} and close shutter')

    yield from pdf_RE_inner(area_det)




def pila_3pos_mu(dets, exposure, md):
    grand_plan = pila_3pos(dets, exposure, extra_md=md)
    grand_plan = bpp.msg_mutator(grand_plan, _inject_pilatus_3pos)
    # grand_plan = bpp.msg_mutator(grand_plan, _inject_calibration_md)
    # grand_plan = bpp.msg_mutator(grand_plan, _inject_analysis_stage)
    return (yield from grand_plan)




## The following plans desgiend for pilatus jogging by CHLin on 2025/08/27
def repeat_count(detectors, num=1, delay=None, *, per_shot=None, md=None):
    """
    Take one or more readings from detectors.
    Parameters
    ----------
    detectors : list
        list of 'readable' objects
    num : integer, optional
        number of readings to take; default is 1
        If None, capture data until canceled
    delay : iterable or scalar, optional
        Time delay in seconds between successive readings; default is 0.
    per_shot : callable, optional
        hook for customizing action of inner loop (messages per step)
        Expected signature ::
           def f(detectors: Iterable[OphydObj]) -> Generator[Msg]:
               ...
    md : dict, optional
        metadata
    Notes
    -----
    If ``delay`` is an iterable, it must have at least ``num - 1`` entries or
    the plan will raise a ``ValueError`` during iteration.
    """
    if num is None:
        num_intervals = None
    else:
        num_intervals = num - 1
    _md = {
        "detectors": [det.name for det in detectors],
        "num_points": num,
        "num_intervals": num_intervals,
        "plan_args": {"detectors": list(map(repr, detectors)), "num": num},
        "hints": {},
    }
    _md.update(md or {})
    _md["hints"].setdefault("dimensions", [(("time",), "primary")])

    if per_shot is None:
        per_shot = bps.one_shot

    @bpp.stage_decorator(detectors)
    @bpp.run_decorator(md=_md)
    def inner_count():
        return (
            yield from bps.repeat(partial(per_shot, detectors), num=num, delay=delay)
        )

    return (yield from inner_count())



def _configure_frame_acq_time(area_det, new_frame_acq_time):
    """function to configure frame acquire time of area detector
        Adeapted from xpdacq.xpdacq_conf.configure_frame_acq_time
        by CHL 2026/03/12
    """
    # stop acquisition
    yield from bps.mv(area_det.cam.acquire, 0)
    yield from bps.sleep(1)
    
    if hasattr(area_det, 'number_of_sets'):
        yield from bps.mv(area_det.number_of_sets, 1)
    
    yield from bps.mv(area_det.cam.acquire_time, new_frame_acq_time)
    
    # extra wait time for device to set
    yield from bps.sleep(1)
    yield from bps.mv(area_det.cam.acquire, 1)
    
    print(
        "INFO: area detector has been configured to new "
        "acquisition time (time per frame)  = {}s".format(new_frame_acq_time)
    )




## A pre-plan to configure the area detector
def _pre_plan(dets, exposure, frame_acq_time=None):
    """Handle detector exposure time + xpdan required metadata"""

    try:
        xpd_configuration["area_det"] = dets[0]

    except (NameError, KeyError):
        pass

    
    ## Change frame acquisition time (not using glbl)
    if (type(frame_acq_time) is float) or (type(frame_acq_time) is int):
        for det in dets:
            if frame_acq_time == det.cam.acquire_time.get():
                pass
            else:
                yield from _configure_frame_acq_time(det, frame_acq_time)


    # if 'pilatus1' not in dets[0].name:
    #     raise ValueError('This plan is for pilatus but not pilatus in dets')

    # setting up area_detector
    # from xpdacq.beamtime import _configure_area_det
    for ad in (d for d in dets if hasattr(d, "cam")):
        (num_frame, acq_time, computed_exposure) = yield from _configure_area_det(exposure)
    # else:
    #     acq_time = 0
    #     computed_exposure = exposure
    #     num_frame = 0

    sp = {
        "time_per_frame": acq_time,
        "num_frames": num_frame,
        "requested_exposure": exposure,
        "computed_exposure": computed_exposure,
        "type": "generator",
        "uid": str(uuid.uuid4()),
        "plan_name": "bps.trigger",
    }

    _md = ChainMap(
        {
            "sp_time_per_frame": acq_time,
            "sp_num_frames": num_frame,
            "sp_requested_exposure": exposure,
            "sp_computed_exposure": computed_exposure,
            "sp_type": "bps.trigger",
            "sp_uid": str(uuid.uuid4()),
            "sp_plan_name": "trigger",
            "sp_detector": dets[0].name,
            "detectors": [area_det.name for area_det in dets],
            # "data_keys": "pe1c_image",
        },
    )

    # update md
    # _md.update({"sp": sp, **{f"sp_{k}": v for k, v in sp.items()}})
    _md.update({"sp": sp, })
    print(_md)

    return _md



## Another pre-plan to define the 3 positions of pilatus
def pre_pila_3pos(dets, ):

    #det_x_pos = [40.644, 31.356, 36] - MA detector mounting is different 07/04/2025
    det_x_pos = [20.644, 11.356, 16]
    det_y_pos = [-3.356, -12.644, -8]

    ## since repeat_count already has the below 2 decorators so skipped here by CHL on 2025/08/25
    # @bpp.stage_decorator([area_det]+motors)
    # @bpp.run_decorator(md=_md)
    def inner_scan(dets, det_x_pos=det_x_pos, det_y_pos=det_y_pos):
        def trigger_and_wait(stream_name, wait=True):
            for det in dets:
                ret = {}
                yield from bps.trigger(det, wait=wait)
                yield from bps.create(name=stream_name)
                # reading = (yield from bps.read(det))
                # # print(f"reading = {reading}")
                # ret.update(reading)
                yield from bps.read(det)
                yield from bps.read(Grid_X)
                yield from bps.read(Grid_Y)
                yield from bps.save()

        for i in range(len(det_x_pos)):
            ## The below two lines are just for test and need to be commented afterwards by CHLin 2025/08/29
            print(f'num of pila_img{i = }')
            # yield from bps.mvr(OT_stage_2_X_hinted, 1, wait=True) ## for testing when not want to move pilatus
            yield from bps.mv(Grid_X, det_x_pos[i], Grid_Y, det_y_pos[i])

            yield from periodic_dark(trigger_and_wait(f"{dets[0].name}_pos{i}", wait=True))

    # inner_scan_msg_mutator =
    yield from inner_scan(dets, det_x_pos=det_x_pos, det_y_pos=det_y_pos)




## Revise jog for pilatus 3-position scan
## The motor will keep jogging while Pilatus is moving b/w 3 positions
## Another updated jog plan for jog in each position is jog_pila2
def jog_pila(dets, exposure, motor, start, stop, *, num=1, md=None):
    """Take a count while "rocking" the y-position"""
    _md = md or {}
    sp_md = yield from _pre_plan(dets, exposure)
    _md.update(sp_md)
    _md["plan_name"] = "jog_pila_3pos"
    _md["jog_md"] = {"start": start, "stop": stop, "motor": motor.name}

    @bpp.reset_positions_decorator([motor.velocity])
    def per_shot(dets):
        nonlocal start, stop
        yield from bps.mv(motor, start)  # got to initial position
        yield from bps.mv(motor.velocity, abs(stop - start) / (exposure*3.0+1.0), timeout=1)  # set velocity
        gp = short_uid("rocker")
        yield from bps.abs_set(motor, stop, group=gp)  # set motor to move towards end
        # yield from bps.trigger_and_read(dets)  # collect off detector
        yield from pre_pila_3pos(dets, )
        yield from bps.wait(group=gp)
        start, stop = stop, start

    return (yield from repeat_count(dets, md=_md,
                                    per_shot=per_shot if start != stop else bps.trigger_and_read,
                                    num=num))




## Put jog into each position for pilatus 3-position scan
def jog_pila2(dets, exposure, motor, start, stop, *, num=1, md={}):
    """Take a count while "rocking" the y-position"""

    det_x_pos = [20.644, 11.356, 16]
    det_y_pos = [-3.356, -12.644, -8]

    if 'det_x_pos' in md.keys():
        det_x_pos = md['det_x_pos']

    if 'det_y_pos' in md.keys():
        det_y_pos = md['det_y_pos']

    _md = md or {}
    sp_md = yield from _pre_plan(dets, exposure)
    _md.update(sp_md)
    _md["plan_name"] = "jog_pila_3pos"
    _md["jog_md"] = {"start": start, "stop": stop, "motor": motor.name}


    # nonlocal start, stop
    @bpp.reset_positions_decorator([motor.velocity])
    def inner_jog(gp, motor=motor, start=start, stop=stop):
        yield from bps.mv(motor, start)  # got to initial position
        yield from bps.mv(motor.velocity, abs(stop-start)/(exposure+2.0), timeout=1)  # set velocity
        # gp = short_uid("rocker")
        yield from bps.abs_set(motor, stop, group=gp)  # set motor to move towards end


    def per_shot(dets):

        def trigger_and_wait(stream_name, wait=True):
            for det in dets:
                ret = {}
                yield from bps.trigger(det, wait=wait)
                yield from bps.create(name=stream_name)
                yield from bps.read(det)
                yield from bps.read(Grid_X)
                yield from bps.read(Grid_Y)
                yield from bps.save()

        nonlocal motor, start, stop
        for i in range(len(det_x_pos)):
            print(f'num of pila_img{i = }')
            yield from bps.mv(Grid_X, det_x_pos[i], Grid_Y, det_y_pos[i])

            gp = short_uid("rocker")
            yield from inner_jog(gp, motor=motor, start=start, stop=stop)

            yield from bps.mv(fs, 1)
            print(f'Open shutter for Pilatus position {i}')
            yield from periodic_dark(trigger_and_wait(f"{dets[0].name}_pos{i}", wait=True))
            yield from bps.mv(fs, 0)
            print(f'Finish Pilatus position {i} and close shutter')

            yield from bps.wait(group=gp)
            # start, stop = stop, start

    return (yield from repeat_count(dets, md=_md,
                                    per_shot=per_shot if start != stop else bps.trigger_and_read,
                                    num=num))




def jog_loop(exposure, motor, start, stop):

    yield from bps.mv(motor, start)  # go to initial position

    motor_max_velocity = 5 #motor.VMAX.get() # read from ophyd object
    jog_distance = motor_max_velocity * exposure
    print(f'{jog_distance = } mm/s')
    sample_distance = abs(stop-start)
    print(f'{sample_distance = } mm')
    num_jogging = int(jog_distance/sample_distance)

    @bpp.stage_decorator([motor])
    def inner_jog(motor=motor, start=start, stop=stop, jog_distance=jog_distance, sample_distance=sample_distance):
        gp = short_uid("rocker")
        for i in range(num_jogging):
        # while jog_distance-sample_distance > 0:
            yield from bps.abs_set(motor, stop, )  # set motor to move towards end
            yield from bps.abs_set(motor, start, )  # go to initial position
            # yield from bps.mv(motor, start, )  # set motor to move towards end

            jog_distance -= sample_distance
            print(f'{jog_distance = } mm/s')

        yield from bps.wait(group=gp)

    yield from inner_jog()  # set motor to move towards end





def tirgger_pila_3pos(dets, exposure, md, jogging=[], user_config={}):

    _md = md or {}
    # _md['sample_name'] = sample_name
    sp_md = yield from _pre_plan(dets, exposure)
    sp_md["sp_plan_name"] = "tirgger_pila",
    _md.update(sp_md)
    _md.update({'user_config':user_config})

    if len(jogging) == 3:
        _md["plan_name"] = "jog_pila_3pos"
        _md["jog_md"] = {"start": jogging[1], "stop": jogging[2], "motor": jogging[0].name}
        jogging_motor = jogging[0]
    else:
        jogging_motor = OT_stage_2_Y

    # #det_x_pos = [40.644, 31.356, 36] - MA detector mounting is different 07/04/2025
    det_x_pos = [20.644, 11.356, 16]
    det_y_pos = [-3.356, -12.644, -8]

    # ## New 3 positions for WAXS+SAXS
    # x0 = 13.11075
    # y0 = -9.074
    # det_x_pos = [x0-27*0.172*1, x0-27*0.172*2, x0-27*0.172*3]
    # det_y_pos = [y0+27*0.172*1, y0+27*0.172*2, y0+27*0.172*3]

    if 'det_x_pos' in md.keys():
        det_x_pos = md['det_x_pos']

    if 'det_y_pos' in md.keys():
        det_y_pos = md['det_y_pos']

    if 'pilatus' in dets[0].name:
        motors = [Grid_X, Grid_Y, Grid_Z]
        motors_field = ['Grid_X', 'Grid_Y', 'Grid_Z']
    else:
        print(f'pilatus not in {dets[0].name = }, set motors and motors_field to []')
        motors = []
        motors_field = []


    # nonlocal start, stop
    @bpp.reset_positions_decorator([jogging_motor.velocity])
    def inner_jog(gp, motor, start, stop):
        yield from bps.mv(motor, start)  # got to initial position
        yield from bps.mv(motor.velocity, abs(stop-start)/(exposure), timeout=1)  # set velocity
        # gp = short_uid("rocker")
        yield from bps.abs_set(motor, stop, group=gp)  # set motor to move towards end

    
    @bpp.stage_decorator(dets+motors)
    @bpp.run_decorator(md=_md)
    def _RE_inner(dets, motors, det_x_pos, det_y_pos):

        def trigger_and_wait(stream_name) -> MsgGenerator:
            
            # Pass an empty list of columns to show simply ‘time’ and ‘seq_num’ (sequence number).
            # https://nsls-ii.github.io/bluesky/callbacks.html#ways-to-invoke-callbacks
            table = LiveTable(motors_field, stream_name=stream_name, )
            @bpp.subs_decorator(table)
            def _inner_trigger()-> MsgGenerator:
                for det in dets:
                    yield from bps.trigger(det, wait=True)
                    yield from bps.create(name=stream_name)
                    yield from bps.read(det)
                    yield from bps.read(motors[0])
                    yield from bps.read(motors[1])
                    yield from bps.read(motors[2])
                    # ret = {}
                    # reading = (yield from bps.read(det))
                    # print(f"reading = {reading}")
                    # ret.update(reading)
                    # return (yield from bps.save())
                    yield from bps.save()
            
            yield from _inner_trigger()
            
        def _trigger_3pos():
            nonlocal jogging
            for i in range(len(det_x_pos)):
                yield from bps.mv(motors[0], det_x_pos[i], motors[1], det_y_pos[i])

                if len(jogging) == 3:
                    print(f'Star to jog using {jogging[0].name} from {jogging[1]} mm to {jogging[2]} mm')
                    gp = short_uid("rocker")
                    yield from inner_jog(gp, motor=jogging[0], start=jogging[1], stop=jogging[2])

                yield from bps.mv(fs, 1)
                print(f'\nOpen shutter for Pilatus position {i}')
                # yield from periodic_dark(trigger_and_wait(f"{dets[0].name}_pos{i}"))
                yield from trigger_and_wait(f"{dets[0].name}_pos{i}")
                yield from bps.mv(fs, 0)
                print(f'Finish Pilatus position {i} and close shutter\n')

        yield from _trigger_3pos()

    return (yield from _RE_inner(dets, motors, det_x_pos, det_y_pos))





def trigger_areaDet(dets, exposure, stream_name, md, no_dark, jogging=[], frame_acq_time=None, user_config={}):
    _md = md or {}
    # _md['sample_name'] = sample_name
    sp_md = yield from _pre_plan(dets, exposure, frame_acq_time=frame_acq_time)
    sp_md["sp_plan_name"] = "trigger_areaDet",
    _md.update(sp_md)
    _md.update({'user_config':user_config})

    if len(jogging) == 3:
        _md["plan_name"] = "jog_areaDet"
        _md["jog_md"] = {"start": jogging[1], "stop": jogging[2], "motor": jogging[0].name}
        jogging_motor = jogging[0]
    else:
        jogging_motor = OT_stage_2_Y

    if 'pilatus' in dets[0].name:
        motors = [Grid_X, Grid_Y, Grid_Z]
        motors_field = ['Grid_X', 'Grid_Y', 'Grid_Z']
    
    elif 'pe1' in dets[0].name:
        motors = [Det_1_X, Det_1_Y, Det_1_Z]
        motors_field = ['Det_1_X', 'Det_1_Y', 'Det_1_Z']
    
    else:
        print(f'pilatus or pe1 not in {dets[0].name = }, set motors and motors_field to []')
        motors = []
        motors_field = []



    # nonlocal start, stop
    @bpp.reset_positions_decorator([jogging_motor.velocity])
    def inner_jog(gp, motor, start, stop):
        yield from bps.mv(motor, start)  # got to initial position
        yield from bps.mv(motor.velocity, abs(stop-start)/(exposure), timeout=1)  # set velocity
        # gp = short_uid("rocker")
        yield from bps.abs_set(motor, stop, group=gp)  # set motor to move towards end


    table = LiveTable(motors_field, stream_name=stream_name, default_prec=0)
    # @bpp.subs_decorator(table)
    @bpp.stage_decorator(dets)
    @bpp.run_decorator(md=_md)
    def trigger_and_wait() -> MsgGenerator:
        for det in dets:

            nonlocal jogging
            if len(jogging) == 3:
                print(f'Star to jog using {jogging[0].name} from {jogging[1]} mm to {jogging[2]} mm')
                gp = short_uid("rocker")
                yield from inner_jog(gp, motor=jogging[0], start=jogging[1], stop=jogging[2])

            yield from bps.mv(fs, 1)
            print(f'\nOpen shutter to start the run....')

            yield from bps.trigger(det, wait=True)
            yield from bps.create(name=stream_name)
            yield from bps.read(det)

            try: 
                yield from bps.read(motors[0])
                yield from bps.read(motors[1])
                yield from bps.read(motors[2])

            except IndexError:
                print(f'\nNo Corresponding motros for the detector.')
    
            yield from bps.save()

            yield from bps.mv(fs, 0)
            print(f'\nClose shutter to finish the run....')
    
    if not no_dark:
        return (yield from periodic_dark(trigger_and_wait()))
    else:
        return (yield from trigger_and_wait())


def simple_trigger(dets, md=None, open_fs=True, close_fs=True):
    _md = md or {}
    @bpp.stage_decorator(dets)
    @bpp.run_decorator(md=_md)
    def trigger_and_wait() -> MsgGenerator:

        for det in dets:

            if open_fs:
                yield from bps.mv(fs, 1)
                print(f'\nOpen shutter to start the run....')

            yield from bps.trigger(det, wait=True)
            yield from bps.create(name='primary')
            # yield from bps.read(det)
            # yield from bps.read(motors[0])
            # yield from bps.read(motors[1])
            # yield from bps.read(motors[2])
            ret = {}
            reading = (yield from bps.read(det))
            ret.update(reading)
            print(f'{ret = }')
            yield from bps.save()

            if close_fs:
                yield from bps.mv(fs, 0)
                print(f'\nClose shutter to finish the run....')

    yield from trigger_and_wait()



from xpdacq.xpdacq import _inject_qualified_dark_frame_uid, _inject_calibration_md, _inject_analysis_stage

def scan_with_dark(dets: list, 
                   exposure: float=0.1, 
                   sample_ID: int=0, 
                   sample_info: dict={}, 
                   md: dict={}, 
                   stream_name: str='primary', 
                   no_dark: bool=False, 
                   jogging:list=[], 
                   frame_acq_time: float=0.1, 
                   user_config: dict={},
                   ):
    """Take a scan with an aera detector for PDF or XRD

    Args:
        dets (list): 
            list of detector ophyd object, e.g., [piatus1] or [pe1c]

        exposure (float, optional): 
            total exposure (measurement) time in seconds.  
            Defaults to 0.1.

        sample_ID (int, optional): 
            sample index returned in bt.list(). 
            Defaults to 0.

        sample_info (list, optional): 
            when sample_ID is not given or found, pass sample_name and composition_string in a list here.
            sample_name as the first, composition_string as the second
            e.g., sample_info = ['CeO2_quartz', 'CeO2']
            Defaults to [].

        md (dict, optional): 
            additional metadata.
            e.g., md = {'note':'dummy test'} 
            Defaults to {}.

        stream_name (str, optional): 
            stream name in the event document, 'primary' is recommended.
            Defaults to 'primary'.

        no_dark (bool, optional): 
            if no_dark = True, the dark scan will be skipped, especially for pilatus. 
            Defaults to False.

        jogging (list, optional): 
            If jogging, three elemetns needs to be defined as [jog_motor, start, stop].
            e.g.,  jogging = [OT_stage_2_X, 0.5, 3.7]
            Defaults to [].

        frame_acq_time (float, optional): 
            Change frame acquistion time if needed, only for pe1c. 
            Defaults to 0.1.

        user_config (dict, optional): 
            Pass self-defined configuration info to pdfstream.
            e.g.,  user_config = {'auto_mask': False, 'qmaxinst':28, 'qmax':28.0, 'rpoly':0.7,
                    'user_mask': '/nsls2/auto-storage/pdf/pdfhack/legacy/processed/xpdacq_data/user_data/config_base/Mask.npy',    
                    'method': 'splitpixel'}
            Defaults to {}.

    Returns:
        str: uid

    Yields:
        msg: Msg
    """

    ## Inject sample metadata from Excel spreadsheet
    try:
        sample_meta:dict = bt.samples.sel(sample_ID)

    ## Inject sample metadata manually from sample_info
    except (KeyError, IndexError):
        sample_meta:dict = {}
        sample_meta['sample_name'] = sample_info[0]
        sample_meta['composition_string'] = sample_info[1]

    print(f'\n***** sample_name = {sample_meta["sample_name"]} *****')

    ## Check composition string
    try:
        print(f'\n***** composition_string = {sample_meta["composition_string"]} *****\n')
    except KeyError:
        sample_meta["composition_string"] = 'Ni1.0'
        print(f'\n***** composition_string = {sample_meta["composition_string"]} (dummy) *****\n')

    md.update(sample_meta)

    ## while passing plan as a generator, no need to add "yield from"
    grand_plan = trigger_areaDet(dets, exposure, stream_name, md, no_dark, 
                                 jogging=jogging, frame_acq_time=frame_acq_time, 
                                 user_config=user_config)
    
    if not no_dark:
        grand_plan = bpp.msg_mutator(grand_plan, _inject_qualified_dark_frame_uid)
    
    grand_plan = bpp.msg_mutator(grand_plan, _inject_calibration_md)
    grand_plan = bpp.msg_mutator(grand_plan, _inject_analysis_stage)
    return (yield from grand_plan)




## Updated by CHLin on 2025/11/18
def scan_pila_3pos(dets: list, 
                   exposure: float=0.1, 
                   sample_ID: int=0, 
                   sample_info: dict={}, 
                   md: dict={}, 
                   jogging: list=[], 
                   user_config: dict={}, 
                   ):
    
    """Take 3 scans at 3 different dectecto positions for PDF or XRD, especially for pilatus

    Args:
        dets (list): 
            list of detector ophyd object, e.g., [piatus1] or [pe1c]

        exposure (float, optional): 
            total exposure (measurement) time in seconds.
            Defaults to 0.1.

        sample_ID (int, optional): 
            sample index returned in bt.list(). 
            Defaults to 0.

        sample_info (list, optional): 
            when sample_ID is not given or found, pass sample_name and composition_string in a list here.
            sample_name as the first, composition_string as the second
            e.g., sample_info = ['CeO2_quartz', 'CeO2']
            Defaults to [].

        md (dict, optional): 
            additional metadata.
            e.g., md = {'note':'dummy test'} 
            Defaults to {}.

        jogging (list, optional): 
            If jogging, three elemetns needs to be defined as [jog_motor, start, stop].
            e.g.,  jogging = [OT_stage_2_X, 0.5, 3.7]
            Defaults to [].

        user_config (dict, optional): 
            Pass self-defined configuration info to pdfstream.
            e.g.,  user_config = {'auto_mask': False, 'qmaxinst':28, 'qmax':28.0, 'rpoly':0.7,
                    'user_mask': '/nsls2/auto-storage/pdf/pdfhack/legacy/processed/xpdacq_data/user_data/config_base/Mask.npy',    
                    'method': 'splitpixel'}
            Defaults to {}.

    Returns:
        str: uid

    Yields:
        msg: Msg
    """

    ## Inject sample metadata from Excel spreadsheet
    try:
        sample_meta:dict = bt.samples.sel(sample_ID)

    ## Inject sample metadata manually from sample_info
    except (KeyError, IndexError):
        sample_meta:dict = {}
        sample_meta['sample_name'] = sample_info[0]
        sample_meta['composition_string'] = sample_info[1]

    print(f'\n***** sample_name = {sample_meta["sample_name"]} *****')

    ## Check composition string
    try:
        print(f'\n***** composition_string = {sample_meta["composition_string"]} *****\n')
    except KeyError:
        sample_meta["composition_string"] = 'Ni1.0'
        print(f'\n***** composition_string = {sample_meta["composition_string"]} (dummy) *****\n')

    md.update(sample_meta)

    ## while passing plan as a generator, no need to add "yield from"
    grand_plan = tirgger_pila_3pos(dets, exposure, md, 
                                   jogging=jogging, user_config=user_config)
    # grand_plan = bpp.msg_mutator(grand_plan, _inject_qualified_dark_frame_uid)
    grand_plan = bpp.msg_mutator(grand_plan, _inject_calibration_md)
    grand_plan = bpp.msg_mutator(grand_plan, _inject_analysis_stage)
    return (yield from grand_plan)



def pd_counts(dets, exposure, sample_name='test', md=None):
    _md = md or {}
    _md['sample_name'] = sample_name
    sp_md = yield from _pre_plan(dets, exposure)
    # sp_md = {}
    sp_md["sp_plan_name"] = "pd_counts"
    _md.update(sp_md)

    yield from periodic_dark(count(dets, md=_md))


import h5py
from skimage import io
def nxs_to_tiff(fn:str, key:str=None, return_sum:bool=False):
    if key is None:
        key = 'entry/instrument/detector/data'

    f_h5 = h5py.File(fn, 'r')
    data =  np.asarray(f_h5['entry/instrument/detector/data'], dtype=np.float32)

    if return_sum:
        data = np.mean(data, axis=0, dtype=np.float32)
        out_fn = f'{fn[:-4]}.tiff'
        io.imsave(out_fn, data)
    else:
        for i in range(data.shape[0]):
            out_fn = f'{fn[:-4]}_{i:02d}.tiff'
            io.imsave(out_fn, data[i])

    return data



class Cam(AreaDetector):
    # pass

    acquire = Cpt(EpicsSignal, 'cam1:Acquire')
    expousre_time = Cpt(EpicsSignal, 'cam1:AcquireTime', kind = 'config')
    acquire_period = Cpt(EpicsSignal, 'cam1:AcquirePeriod', kind = 'config')
    num_exposure = Cpt(EpicsSignal, 'cam1:NumExposures', kind = 'config')
    ArrayData = Cpt(EpicsSignal, 'image1:ArrayData', kind = 'normal')
    # ArraySize1 = Cpt(EpicsSignalRO, 'image1:ArraySize1_RBV', kind = 'config')
    # ArraySize2 = Cpt(EpicsSignalRO, 'image1:ArraySize2_RBV', kind = 'config')
    ArraySize0 = Cpt(EpicsSignalRO, 'TIFF1:ArraySize0_RBV', kind = 'config')
    ArraySize1 = Cpt(EpicsSignalRO, 'TIFF1:ArraySize1_RBV', kind = 'config')
    ArraySize2 = Cpt(EpicsSignalRO, 'TIFF1:ArraySize2_RBV', kind = 'config')

    # image = Cpt(ImagePlugin, 'image1:', kind = 'normal')
    # tiff = Cpt(TIFFPlugin, 'TIFF1:',
    #         write_path_template='/nsls2/data/pdf/legacy/raw/cam1/%Y/%m/%d/',
    #         root='/nsls2/data/pdf/legacy/raw')

    def grab_frame(self):

        def is_done(value, old_value, **kwargs):
            if old_value == 1 and value ==0:
                return True
            return False

        # status = SubscriptionStatus(self.acquire, run=False, callback=is_done)
        status = SubscriptionStatus(self.ArrayData, run=False, callback=is_done)

        # self.acquire.put(1)
        self.ArrayData.get()
        return status

    def trigger(self):
        #self.grab_frame().wait()
        # return self.grab_frame()
        # return (yield from self.grab_frame2())
        return self.grab_frame()



# Cam1 = Cam('XF:28ID1-BI{Cam:1}', name='Cam1')


def save_Cam1_tiff(is_plot=True, is_save=True):
    new_shape = (Cam1.ArraySize2.get(), Cam1.ArraySize1.get(), Cam1.ArraySize0.get())
    data = np.reshape(Cam1.ArrayData.get(), new_shape)

    if is_plot:
        plt.figure()
        plt.imshow(data.mean(axis=2, dtype=np.float32))

    if is_save:
        fn_path = '/home/xf28id1/Documents/raw/cam1'
        fn_name = auto_name_file('', '.tiff', fn_path)
        skimage.io.imsave(fn_name, data.mean(axis=2, dtype=np.float32))



class PDFCam1(AreaDetector):
    image = Cpt(ImagePlugin, 'image1:')
    _default_configuration_attrs = (
        AreaDetector._default_configuration_attrs +
        ('images_per_set', 'number_of_sets'))

    tiff = Cpt(XPDTIFFPlugin, 'TIFF1:', #- MA
             #write_path_template='Z:/data/pe1_data/%Y/%m/%d', #- DO
             #write_path_template='J:\\%Y\\%m\\%d\\', #- DO
             #write_path_template='Z:/img/%Y/%m/%d/', #- MA
            #  write_path_template='/home/xf28id1/Documents/raw/cam1/temp/', # CHL
             write_path_template='/nsls2/data/pdf/legacy/raw/cam1/',
             #read_path_template='/SHARE/img/%Y/%m/%d/', #- MA
             #read_path_template='/nsls2/data/pdf/legacy/raw/cam1/%Y/%m/%d/', #- DO
            #  read_path_template='/home/xf28id1/Documents/raw/cam1/temp/',  # CHL
             read_path_template='/nsls2/data/pdf/legacy/raw/cam1/',  # CHL
             #root='/nsls2/data/pdf/legacy/raw/cam1/', #-DO
             #root='/SHARE/img/', #-MA
            #  root='/home/xf28id1/Documents/raw/cam1/temp/',  # CHL
             root='/nsls2/data/pdf/legacy/raw/cam1/',
             cam_name='cam',  # used to configure "tiff squashing" #-MA
             proc_name='proc',  # ditto #-MA
             read_attrs=[]) #- MA
    # hdf5 = C(XPDHDF5Plugin, 'HDF1:',
    #          write_path_template='G:/pe1_data/%Y/%m/%d/',
    #          read_path_template='/direct/XF28ID2/pe1_data/%Y/%m/%d/',
    #          root='/direct/XF28ID2/', reg=db.reg)

    proc = Cpt(ProcessPlugin, 'Proc1:')

    # These attributes together replace `num_images`. They control
    # summing images before they are stored by the detector (a.k.a. "tiff
    # squashing").
    detector_type = Cpt(Signal, value='Perkin', kind='config')
    images_per_set = Cpt(Signal, value=1, add_prefix=())
    number_of_sets = Cpt(Signal, value=1, add_prefix=())

    stats1 = Cpt(StatsPluginV33, 'Stats1:')
    stats2 = Cpt(StatsPluginV33, 'Stats2:')
    stats3 = Cpt(StatsPluginV33, 'Stats3:')
    stats4 = Cpt(StatsPluginV33, 'Stats4:')
    stats5 = Cpt(StatsPluginV33, 'Stats5:')

    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')

    # dark_image = C(SavedImageSignal, None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([(self.cam.trigger_mode, 'Internal'),
                               ])



class Cam_2(ContinuousAcquisitionTrigger, PDFCam1):
    pass


# Cam2 = Cam_2('XF:28ID1-BI{Cam:1}', name='Cam2', read_attrs=['tiff', 'stats1.total'],
#             plugin_name='tiff')


# from ophyd.areadetector.trigger_mixins import SingleTrigger
# from ophyd.areadetector.detectors import PvcamDetector, AreaDetector

# class MyDetector(SingleTrigger, Cam):
#     pass

# prefix = 'XF:28ID1-BI{Cam:1}'
# CamS = MyDetector(prefix, name='CamS')


# def cam_BS_scan(det, md=None):
#     # det = Cam1
#     _md = {}
#     _md.update(md or {})

#     @bpp.stage_decorator([det])
#     @bpp.run_decorator(md=_md)
#     def trigger_detector():  # TODO: rename appropriately
#         ret = {}
#         yield from bps.trigger(det, wait=True)
#         yield from bps.create(name="Cam1_RE")
#         reading = (yield from bps.read(det))
#         # print(f"reading = {reading}")
#         ret.update(reading)
#         yield from bps.save()
#     yield from trigger_detector()




def scan_shifter_saxs(
    motor,
    xmin,
    xmax,
    numx,
    num_samples=0,
    min_height=0.02,
    min_dist=5,
    peak_rad=1.5,
    use_det=True,
    abs_data = False,
    oset_data = 0.0,
    return_to_start = True,
    recover_last_scan = False,
    use_pe2c = True,
):
    
    xpd_configuration['area_det']=pe2c

    print('Since using PE2, set frame_acq_time = 0.2 s')
    glbl['frame_acq_time']=.2
    
    def yn_question(q):
        return input(q).lower().strip()[0] == "y"

    init_pos = motor.position

    print("")
    if not recover_last_scan:
        print("I'm going to move the motor: " + str(motor.name))
        print("It's currently at position: " + str(motor.position))
        move_coord = float(xmin) - float(motor.position)
        if move_coord < 0:
            print(
                "So I will start by moving "
                + str(abs(move_coord))[:4]
                + " mm inboard from current location"
            )
        elif move_coord > 0:
            print(
                "So I will start by moving "
                + str(abs(move_coord))[:4]
                + " mm outboard from current location"
            )
        elif move_coord == 0:
            print("I'm starting where I am right now :)")
        else:
            print("I confused")

        if not yn_question("Confirm scan? [y/n] "):
            print("Aborting operation")
            return None

        pos_list, I_list = _motor_move_scan_shifter_pos(
            motor=motor, xmin=xmin, xmax=xmax, numx=numx, use_pe2c=use_pe2c)
    else:
        print ('recovering last scan from redis...')
        return_to_start = False
        pos_list, I_list = retrieve_recent_shifter_scan()
        plt.figure()
        plt.plot(pos_list, I_list)

    if len(pos_list) > 1:
        delx = pos_list[1] - pos_list[0]
    else:
        print("only a single point? I'm gonna quit!")
        return None

    if return_to_start:
        print ('returning to start position....')
        motor.move(init_pos)


    if oset_data != 0.0:
        I_list = I_list - oset_data

    if abs_data:
        I_list = abs(I_list)

    print("")
    if not yn_question(
        "Move on to fitting? (if not, I'll return [pos_list, I_list]) [y/n] "
    ):
        return pos_list, I_list
    plt.close()

    go_on = False
    tmin_height = min_height
    tmin_dist = min_dist
    tpeak_rad = peak_rad
    fit_attempts = 1

    while not go_on:
        print("\nI'm going to fit peaks with a min_height of " + str(tmin_height))
        print(
            "and min_dist [index values/real vals] of "
            + str(tmin_dist)
            + " / "
            + str(tmin_dist * delx)
        )
        print("and I'll fit a radius between each peak-center of " + str(tpeak_rad))
        if fit_attempts == 0:
            go_on, peak_cen_list = _identify_peaks_scan_shifter_pos(
                pos_list,
                I_list,
                num_samples=num_samples,
                min_height=tmin_height,
                min_dist=tmin_dist,
                peak_rad=tpeak_rad,
            )
        else:
            go_on, peak_cen_list = _identify_peaks_scan_shifter_pos(
                pos_list,
                I_list,
                num_samples=num_samples,
                min_height=tmin_height,
                min_dist=tmin_dist,
                peak_rad=tpeak_rad,
                open_new_plot=False,
            )
        fit_attempts += 1
        # if yn_question("\nHappy with the fit? [y/n] ") == False:
        if not go_on:
            qans = input(
                "\n1. Change min_height\n2. Change min_dist\n3. Change peak-fit rad\n0. Give up\n : "
            )
            try:
                qans = int(qans)
                if int(qans) == 1:
                    tmin_height = float(input("\nWhat is the new min_height value? "))
                if int(qans) == 2:
                    tmin_dist = float(input("\nWhat is the new min_dist value? "))
                if int(qans) == 3:
                    tpeak_rad = float(input("\nWhat is the new peak_rad value? "))
                if int(qans) == 0:
                    print("ok, giving up")
                    return None
            except Exception:
                print("what, what, whaaat?")
        else:
            print("Ok, great.")
            go_on = True

    return peak_cen_list


## use pliatus to get sample position
def scan_shifter_saxs2(
    motor,
    xmin,
    xmax,
    numx,
    num_samples=0,
    min_height=0.02,
    min_dist=5,
    peak_rad=1.5,
    use_det=True,
    abs_data = False,
    oset_data = 0.0,
    return_to_start = True,
    recover_last_scan = False,
):
    
    xpd_configuration['area_det']=pilatus1
    RE(_pre_plan([pilatus1], 0.1, frame_acq_time=None))
    
    # print('Since using PE2, set frame_acq_time = 0.2 s')
    # glbl['frame_acq_time']=.2
    
    def yn_question(q):
        return input(q).lower().strip()[0] == "y"

    init_pos = motor.position

    print("")
    if not recover_last_scan:
        print("I'm going to move the motor: " + str(motor.name))
        print("It's currently at position: " + str(motor.position))
        move_coord = float(xmin) - float(motor.position)
        if move_coord < 0:
            print(
                "So I will start by moving "
                + str(abs(move_coord))[:4]
                + " mm inboard from current location"
            )
        elif move_coord > 0:
            print(
                "So I will start by moving "
                + str(abs(move_coord))[:4]
                + " mm outboard from current location"
            )
        elif move_coord == 0:
            print("I'm starting where I am right now :)")
        else:
            print("I confused")

        if not yn_question("Confirm scan? [y/n] "):
            print("Aborting operation")
            return None

        pos_list, I_list = _motor_move_scan_shifter_pos2(
            motor=motor, xmin=xmin, xmax=xmax, numx=numx,)
    else:
        print ('recovering last scan from redis...')
        return_to_start = False
        pos_list, I_list = retrieve_recent_shifter_scan()
        plt.figure()
        plt.plot(pos_list, I_list)

    if len(pos_list) > 1:
        delx = pos_list[1] - pos_list[0]
    else:
        print("only a single point? I'm gonna quit!")
        return None

    if return_to_start:
        print ('returning to start position....')
        motor.move(init_pos)


    if oset_data != 0.0:
        I_list = I_list - oset_data

    if abs_data:
        I_list = abs(I_list)

    print("")
    if not yn_question(
        "Move on to fitting? (if not, I'll return [pos_list, I_list]) [y/n] "
    ):
        return pos_list, I_list
    plt.close()

    go_on = False
    tmin_height = min_height
    tmin_dist = min_dist
    tpeak_rad = peak_rad
    fit_attempts = 1

    while not go_on:
        print("\nI'm going to fit peaks with a min_height of " + str(tmin_height))
        print(
            "and min_dist [index values/real vals] of "
            + str(tmin_dist)
            + " / "
            + str(tmin_dist * delx)
        )
        print("and I'll fit a radius between each peak-center of " + str(tpeak_rad))
        if fit_attempts == 0:
            go_on, peak_cen_list = _identify_peaks_scan_shifter_pos(
                pos_list,
                I_list,
                num_samples=num_samples,
                min_height=tmin_height,
                min_dist=tmin_dist,
                peak_rad=tpeak_rad,
            )
        else:
            go_on, peak_cen_list = _identify_peaks_scan_shifter_pos(
                pos_list,
                I_list,
                num_samples=num_samples,
                min_height=tmin_height,
                min_dist=tmin_dist,
                peak_rad=tpeak_rad,
                open_new_plot=False,
            )
        fit_attempts += 1
        # if yn_question("\nHappy with the fit? [y/n] ") == False:
        if not go_on:
            qans = input(
                "\n1. Change min_height\n2. Change min_dist\n3. Change peak-fit rad\n0. Give up\n : "
            )
            try:
                qans = int(qans)
                if int(qans) == 1:
                    tmin_height = float(input("\nWhat is the new min_height value? "))
                if int(qans) == 2:
                    tmin_dist = float(input("\nWhat is the new min_dist value? "))
                if int(qans) == 3:
                    tpeak_rad = float(input("\nWhat is the new peak_rad value? "))
                if int(qans) == 0:
                    print("ok, giving up")
                    return None
            except Exception:
                print("what, what, whaaat?")
        else:
            print("Ok, great.")
            go_on = True

    return peak_cen_list



def _read_pilatus_int(uid):
    from tiled.client import from_profile
    tiled_client = from_profile('pdf')
    tiled_client.context.http_client.headers['tiled-qos'] = 'acquisition'
    run = tiled_client[uid]
    img = np.float32(getattr(run, 'primary').read()['pilatus-1_image'].to_numpy()[0][0])

    return float(img.sum())


def _motor_move_scan_shifter_pos2(motor, xmin, xmax, numx):
    from epics import caget
    #ensure shutter is closedi
    print ('closing shutter')
    # RE(mv(fs,"Close"))
    # CHL revised for failed fs on 2025/05/23
    RE(mv(fs, 0))
    I_list = np.zeros(numx)
    dx = (xmax - xmin) / numx
    pos_list = np.linspace(xmin, xmax, numx)
    print ('moving to starting postion')
    RE(mv(motor,pos_list[0]))
    print ('opening shutter')
    # RE(mv(fs, "Open"))
    # CHL revised for failed fs on 2025/05/23
    RE(mv(fs, 1))
    time.sleep(1)
    plt.ion()
    fig1, ax1 = plt.subplots()
    use_det = True
    temp_pos_list = []
    temp_I_list = []
    for i, pos in enumerate(pos_list):
        print("moving to " + str(pos))
        try:
            motor.move(pos)
        except Exception:
            print("well, something bad happened")
            return None

        if use_det == True:
            uid,  = RE(simple_trigger([pilatus1], open_fs=False, close_fs=False))
            my_int = _read_pilatus_int(uid)
            print(f"{my_int = }")

        else:
            my_int = float(caget("XF:28ID1B-OP{Det:1-Det:2}Amp:bkgnd"))

        temp_I_list.append(my_int)
        temp_pos_list.append(pos)
        stow_recent_shifter_scan(temp_pos_list, temp_I_list)

        I_list[i] = my_int
        ax1.scatter(pos, my_int, color="k")
        # fig1.canvas.manager.show()
        # fig1.canvas.flush_events()
        plt.pause(0.01)

    plt.plot(pos_list, I_list)
    # plt.close()
    # RE(mv(fs, "Close"))
    # CHL revised for failed fs on 2025/05/23
    RE(mv(fs, 0))
    stow_recent_shifter_scan(pos_list, I_list)
    return pos_list, I_list


## Output the results of scan_shifter_pos_ask() as a csv file by CHLin 2025/07/07
def fitting_pos_csv(pos_list, save=True, fn_prefix=''):
    df = pd.DataFrame()
    df['fitting_pos'] = pos_list

    if save:
        tiff_base = '/nsls2/auto-storage/pdf/pdfhack/legacy/processed/xpdacq_data/user_data/user_data/tiff_base'
        scan_shifter_dir = os.path.join(tiff_base, 'scan_shifter_pos')
        os.makedirs(scan_shifter_dir, exist_ok=True)
        time_stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        fn = os.path.join(scan_shifter_dir, fn_prefix+'_'+f'{time_stamp}')
        df.to_csv(fn, sep=' ', index=False, float_format='{:.5e}'.format)

    return df


def scan_pos_csv(pos_list, I_list, save=True, fn_prefix=''):
    df = pd.DataFrame()
    df['Stage_position'] = pos_list
    df['Intensity'] = I_list

    if save:
        tiff_base = '/nsls2/auto-storage/pdf/pdfhack/legacy/processed/xpdacq_data/user_data/tiff_base'
        scan_shifter_dir = os.path.join(tiff_base, 'scan_shifter_pos')
        os.makedirs(scan_shifter_dir, exist_ok=True)
        time_stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        fn = os.path.join(scan_shifter_dir, fn_prefix+'_'+f'{time_stamp}')
        df.to_csv(fn, sep=' ', index=False, float_format='{:.5e}'.format)

    return df


## A revision to assign plt.figure by CHL on 2025/098/23
def _motor_move_scan_shifter_pos_f(motor, xmin, xmax, numx, use_pe2c=False, figure=None):
    from epics import caget
    #ensure shutter is closedi
    print ('closing shutter')
    # RE(mv(fs,"Close"))
    # CHL revised for failed fs on 2025/05/23
    RE(mv(fs, 0))
    I_list = np.zeros(numx)
    dx = (xmax - xmin) / numx
    pos_list = np.linspace(xmin, xmax, numx)
    print ('moving to starting postion')
    RE(mv(motor,pos_list[0]))
    print ('opening shutter')
    # RE(mv(fs, "Open"))
    # CHL revised for failed fs on 2025/05/23
    RE(mv(fs, 1))
    time.sleep(1)

    plt.ion()
    ## REvised by CHL on 2025/09/23
    # fig1, ax1 = plt.subplots()
    try:
        fig1 = figure
    except (TypeError, AttributeError):
        fig1, ax1 = plt.subplots()

    fig1.clear()
    ax1 = fig1.gca()
    use_det = True
    temp_pos_list = []
    temp_I_list = []
    for i, pos in enumerate(pos_list):
        print("moving to " + str(pos))
        try:
            motor.move(pos)
        except Exception:
            print("well, something bad happened")
            return None

        if use_det == True:
            my_int = float(caget("XF:28ID1-ES{Det:PE1}Stats2:Total_RBV"))
            if use_pe2c:
                my_int = float(caget("XF:28ID1-ES{Det:PE2}Stats2:Total_RBV"))
                time.sleep(.5)
        else:
            my_int = float(caget("XF:28ID1B-OP{Det:1-Det:2}Amp:bkgnd"))

        temp_I_list.append(my_int)
        temp_pos_list.append(pos)
        stow_recent_shifter_scan(temp_pos_list, temp_I_list)

        I_list[i] = my_int
        ax1.scatter(pos, my_int, color="k")
        plt.pause(0.01)

    # plt.plot(pos_list, I_list)
    ax1.plot(pos_list, I_list)
    # plt.close()
    # RE(mv(fs, "Close"))
    # CHL revised for failed fs on 2025/05/23
    RE(mv(fs, 0))
    stow_recent_shifter_scan(pos_list, I_list)
    return pos_list, I_list



## A revision to disable human interaction by CHLin 2025/07/07
def scan_shifter_pos_ask(
    motor,
    xmin,
    xmax,
    numx,
    num_samples=0,
    min_height=0.02,
    min_dist=5,
    peak_rad=1.5,
    use_det=True,
    abs_data = False,
    flip_data = False,
    oset_data = 0.0,
    return_to_start = True,
    recover_last_scan = False,
    need_interaction = False,
    ):

    def yn_question(q):
        return input(q).lower().strip()[0] == "y"

    init_pos = motor.position

    import matplotlib.pyplot as plt
    ## Create two plt.figure objects for plotting scaaning and fitting figures
    ## Added by CHL on 2025/09/23
    plt.ion()
    f_fitting = plt.figure('Fitting')
    ax = f_fitting.gca()
    plt.cla()
    f_fitting.canvas.draw_idle()
    # f_fitting.canvas.manager.show()
    # f_fitting.canvas.flush_events()

    f_scanning = plt.figure('Scanning')


    print("")
    if not recover_last_scan:
        print("I'm going to move the motor: " + str(motor.name))
        print("It's currently at position: " + str(motor.position))
        move_coord = float(xmin) - float(motor.position)
        if move_coord < 0:
            print(
                "So I will start by moving "
                + str(abs(move_coord))[:4]
                + " mm inboard from current location"
            )
        elif move_coord > 0:
            print(
                "So I will start by moving "
                + str(abs(move_coord))[:4]
                + " mm outboard from current location"
            )
        elif move_coord == 0:
            print("I'm starting where I am right now :)")
        else:
            print("I confused")

        # add need_interaction by CHLin on 2025/07/07
        if need_interaction:
            if not yn_question("Confirm scan? [y/n] "):
                print("Aborting operation")
                return None

        pos_list, I_list = _motor_move_scan_shifter_pos_f(
            motor=motor, xmin=xmin, xmax=xmax, numx=numx, figure=f_scanning)
    else:
        print ('recovering last scan from redis...')
        return_to_start = False
        pos_list, I_list = retrieve_recent_shifter_scan()
        plt.figure()
        plt.plot(pos_list, I_list)

    if len(pos_list) > 1:
        delx = pos_list[1] - pos_list[0]
    else:
        print("only a single point? I'm gonna quit!")
        return None

    if return_to_start:
        print ('returning to start position....')
        motor.move(init_pos)


    if oset_data != 0.0:
        I_list = I_list - oset_data

    if abs_data:
        I_list = abs(I_list)

    if flip_data:
        I_list = -(I_list)

    print("")
    # add need_interaction by CHLin on 2025/07/07
    if need_interaction:
        if not yn_question(
            "Move on to fitting? (if not, I'll return [pos_list, I_list]) [y/n] "
        ):
            return pos_list, I_list

    # plt.close()

    go_on = False
    tmin_height = min_height
    tmin_dist = min_dist
    tpeak_rad = peak_rad
    fit_attempts = 1

    while not go_on:
        print("\nI'm going to fit peaks with a min_height of " + str(tmin_height))
        print(
            "and min_dist [index values/real vals] of "
            + str(tmin_dist)
            + " / "
            + str(tmin_dist * delx)
        )
        print("and I'll fit a radius between each peak-center of " + str(tpeak_rad))
        if fit_attempts == 0:
            go_on, peak_cen_list = _identify_peaks_scan_shifter_pos_ask(
                pos_list,
                I_list,
                num_samples=num_samples,
                min_height=tmin_height,
                min_dist=tmin_dist,
                peak_rad=tpeak_rad,
                need_interaction = need_interaction,
                open_new_plot=False,
                figure=f_fitting,

            )
        else:
            go_on, peak_cen_list = _identify_peaks_scan_shifter_pos_ask(
                pos_list,
                I_list,
                num_samples=num_samples,
                min_height=tmin_height,
                min_dist=tmin_dist,
                peak_rad=tpeak_rad,
                open_new_plot=False,
                need_interaction = need_interaction,
                figure=f_fitting,
            )
        f_fitting.canvas.draw_idle()
        fit_attempts += 1
        # if yn_question("\nHappy with the fit? [y/n] ") == False:

        # add need_interaction by CHLin on 2025/07/07
        if need_interaction:
            if not go_on:
                qans = input(
                    "\n1. Change min_height\n2. Change min_dist\n3. Change peak-fit rad\n0. Give up\n : "
                )
                try:
                    qans = int(qans)
                    if int(qans) == 1:
                        tmin_height = float(input("\nWhat is the new min_height value? "))
                    if int(qans) == 2:
                        tmin_dist = float(input("\nWhat is the new min_dist value? "))
                    if int(qans) == 3:
                        tpeak_rad = float(input("\nWhat is the new peak_rad value? "))
                    if int(qans) == 0:
                        print("ok, giving up")
                        return None
                except Exception:
                    print("what, what, whaaat?")
            else:
                print("Ok, great.")
                go_on = True

    return pos_list, I_list, peak_cen_list


## A revision for output sample position as a csv file by CHLin 2025/07/07
## Modificaiton: remove human intercaation
def _identify_peaks_scan_shifter_pos_ask(
    x, y, num_samples=0, min_height=0.02, min_dist=5, peak_rad=1.5, open_new_plot=True,
    need_interaction = False, figure=None,
):
    from scipy.signal import find_peaks
    import matplotlib.pyplot as plt
    from scipy.optimize import curve_fit
    import numpy as np
    import pandas as pd

    if open_new_plot:
        print("making new figure")
        this_fig = plt.figure()

    else:
        print("clearing figure")

        try:
            this_fig = figure
        except (TypeError, AttributeError):
            this_fig = plt.gcf()

    plt.ion()
    # this_fig.clear()
    this_ax = this_fig.gca()
    plt.pause(0.5)

    def yn_question(q):
        return input(q).lower().strip()[0] == "y"

    y -= y.min()
    y /= y.max()
    print("ymax is " + str(max(y)))
    print("ymin is " + str(min(y)))

    def cut_data(qt, sqt, qmin, qmax):
        qcut = []
        sqcut = []
        for i in range(len(qt)):
            if qt[i] >= qmin and qt[i] <= qmax:
                qcut.append(qt[i])
                sqcut.append(sqt[i])
        qcut = np.array(qcut)
        sqcut = np.array(sqcut)
        return qcut, sqcut

    # initial guess of position peaks
    print("finding things")
    peaks, _ = find_peaks(y, height=min_height, distance=min_dist)

    if num_samples == 0:
        print("I found " + str(len(peaks)) + " peaks.")
    elif num_samples == len(peaks):
        print("I think I found all " + str(num_samples) + " samples you expected.")
    else:
        print("WARNING: I saw " + str(len(peaks)) + " samples!")
    print("doing a thing")

    ## plot identified peaks
    # this_ax.plot(x, y)
    # this_ax.plot(x[peaks], y[peaks], "kx")
    # plt.show()
    # print("done")
    # plt.pause(0.01)

    # add need_interaction by CHLin on 2025/07/07
    if need_interaction:
        if not yn_question("Go on? [y/n] "):
            return False, []

    # now refine positions
    peak_cen_guess_list = x[peaks]
    peak_amp_guess_list = y[peaks]

    fit_peak_cen_list = np.zeros(len(peaks))
    fit_peak_amp_list = np.zeros(len(peaks))
    fit_peak_bgd_list = np.zeros(len(peaks))
    fit_peak_wid_list = np.zeros(len(peaks))

    def this_func(x, c, w, a, b):

        return a * np.exp(-((x - c) ** 2.0) / (2.0 * (w ** 2))) + b

    # this_fig = plt.gcf()
    # this_fig.clf()
    for i in range(len(peaks)):
        cut_x, cut_y = cut_data(
            x, y, peak_cen_guess_list[i] - peak_rad, peak_cen_guess_list[i] + peak_rad
        )
        # plt.plot(cut_x, cut_y)
        this_ax.plot(cut_x, cut_y)

        this_guess = [peak_cen_guess_list[i], 1, peak_amp_guess_list[i], 0.0001]
        low_limits = [peak_cen_guess_list[i] - peak_rad, 0.05, 0.0, 0.0]
        high_limits = [peak_cen_guess_list[i] + peak_rad, 3, 1.5, 0.5]

        popt, _ = curve_fit(
            this_func, cut_x, cut_y, p0=this_guess, bounds=(low_limits, high_limits)
        )
        # plt.plot(cut_x, this_func(cut_x, *popt), "k--")
        this_ax.plot(cut_x, this_func(cut_x, *popt), "k--")

        fit_peak_amp_list[i] = popt[2]
        fit_peak_wid_list[i] = popt[1]
        fit_peak_cen_list[i] = popt[0]
        fit_peak_bgd_list[i] = popt[3]

    # plt.show()
    plt.pause(0.01)

    # finally, return this as a numpy list
    return True, fit_peak_cen_list[::-1]  # return flipped




def pilatus_overnight(num_peat:int =1, wait_time_sec:float =60.0):
    for i in range(num_peat):
        print(f'\n{i = }\n')
        yield from scan_with_dark([pilatus1], exposure=0.1, frame_acq_time=0.1, sample_ID=0, no_dark=True)
        yield from sleep_sec_q(wait_time_sec)
        

# data = np.reshape(Cam1.ArrayData.get(), (Cam1.ArraySize2.get(), Cam1.ArraySize1.get(), Cam1.ArraySize0.get())
# data = np.reshape(Cam1.ArrayData.get(), (Cam1.ArraySize2.get(), Cam1.ArraySize1.get(),3)
# Cam1_TIFF1 = EpicsSignal('XF:28ID1-BI{Cam:1}TIFF1', name='Cam1_TIFF1', kind='normal')



# XF:28ID1-UT{Gas:1-Vlv:IIV_0101A}Cmd


# XF:28ID1-BI{Cam:1}ROI1:MinX
# XF:28ID1-BI{Cam:1}ROI1:MinY
# XF:28ID1-BI{Cam:1}ROI1:SizeX
# XF:28ID1-BI{Cam:1}ROI1:SizeY
# XF:28ID1-BI{Cam:1}ROI2:MinX
# XF:28ID1-BI{Cam:1}ROI2:MinY
# XF:28ID1-BI{Cam:1}ROI2:SizeX
# XF:28ID1-BI{Cam:1}ROI2:SizeY
# XF:28ID1-BI{Cam:1}ROI3:MinX
# XF:28ID1-BI{Cam:1}ROI3:MinY
# XF:28ID1-BI{Cam:1}ROI3:SizeX
# XF:28ID1-BI{Cam:1}ROI3:SizeY
# XF:28ID1-BI{Cam:1}ROI4:MinX
# XF:28ID1-BI{Cam:1}ROI4:MinY
# XF:28ID1-BI{Cam:1}ROI4:SizeX
# XF:28ID1-BI{Cam:1}ROI4:SizeY
# XF:28ID1-BI{Cam:1}Stats1:ComputeHistogram
# XF:28ID1-BI{Cam:1}Stats1:HistSize_RBV
# XF:28ID1-BI{Cam:1}Stats1:Histogram_RBV
# XF:28ID1-BI{Cam:1}Stats1:MaxValue_RBV
# XF:28ID1-BI{Cam:1}Stats1:MeanValue_RBV
# XF:28ID1-BI{Cam:1}Stats1:MinValue_RBV
# XF:28ID1-BI{Cam:1}Stats1:Sigma_RBV
# XF:28ID1-BI{Cam:1}Stats1:Total_RBV
# XF:28ID1-BI{Cam:1}Stats2:Total_RBV
# XF:28ID1-BI{Cam:1}Stats3:Total_RBV
# XF:28ID1-BI{Cam:1}Stats4:Total_RBV
# XF:28ID1-BI{Cam:1}Stats5:Total_RBV
# XF:28ID1-BI{Cam:1}cam1:Acquire
# XF:28ID1-BI{Cam:1}cam1:AcquirePeriod
# XF:28ID1-BI{Cam:1}cam1:AcquirePeriod_RBV
# XF:28ID1-BI{Cam:1}cam1:AcquireTime
# XF:28ID1-BI{Cam:1}cam1:AcquireTime_RBV
# XF:28ID1-BI{Cam:1}cam1:ArrayCounter
# XF:28ID1-BI{Cam:1}cam1:ArrayCounter_RBV
# XF:28ID1-BI{Cam:1}cam1:ArrayRate_RBV
# XF:28ID1-BI{Cam:1}cam1:AsynIO.CNCT
# XF:28ID1-BI{Cam:1}cam1:DetectorState_RBV
# XF:28ID1-BI{Cam:1}cam1:ImageMode
# XF:28ID1-BI{Cam:1}cam1:ImageMode_RBV
# XF:28ID1-BI{Cam:1}cam1:NumExposures
# XF:28ID1-BI{Cam:1}cam1:NumExposures_RBV
# XF:28ID1-BI{Cam:1}cam1:NumImages
# XF:28ID1-BI{Cam:1}cam1:NumImagesCounter_RBV
# XF:28ID1-BI{Cam:1}cam1:NumImages_RBV
# XF:28ID1-BI{Cam:1}cam1:TriggerMode
# XF:28ID1-BI{Cam:1}cam1:TriggerMode_RBV
# XF:28ID1-BI{Cam:1}image1:ArrayData
# XF:28ID1-BI{Cam:1}image1:ArraySize1_RBV
# XF:28ID1-BI{Cam:1}image1:ArraySize2_RBV
# XF:28ID1-CT{IOC:Cam1}:SysReset




# XF:28ID1-BI{Cam:1}TIFF1:ADCoreVersion_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ArrayCallbacks
# XF:28ID1-BI{Cam:1}TIFF1:ArrayCallbacks_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ArrayCounter
# XF:28ID1-BI{Cam:1}TIFF1:ArrayCounter_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ArrayRate_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ArraySize0_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ArraySize1_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ArraySize2_RBV
# XF:28ID1-BI{Cam:1}TIFF1:AutoIncrement
# XF:28ID1-BI{Cam:1}TIFF1:AutoIncrement_RBV
# XF:28ID1-BI{Cam:1}TIFF1:AutoSave
# XF:28ID1-BI{Cam:1}TIFF1:AutoSave_RBV
# XF:28ID1-BI{Cam:1}TIFF1:Capturecam1:AcquirePeriod
# XF:28ID1-BI{Cam:1}TIFF1:Capture_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ColorMode_RBV
# XF:28ID1-BI{Cam:1}TIFF1:CreateDirectory
# XF:28ID1-BI{Cam:1}TIFF1:CreateDirectory_RBV
# XF:28ID1-BI{Cam:1}TIFF1:DataType_RBV
# XF:28ID1-BI{Cam:1}TIFF1:DeleteDriverFile
# XF:28ID1-BI{Cam:1}TIFF1:DeleteDriverFile_RBV
# XF:28ID1-BI{Cam:1}TIFF1:DriverVersion_RBV
# XF:28ID1-BI{Cam:1}TIFF1:DroppedArrays
# XF:28ID1-BI{Cam:1}TIFF1:DroppedArrays_RBV
# XF:28ID1-BI{Cam:1}TIFF1:EnableCallbacks
# XF:28ID1-BI{Cam:1}TIFF1:EnableCallbacks_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ExecutionTime_RBV
# XF:28ID1-BI{Cam:1}TIFF1:FileName
# XF:28ID1-BI{Cam:1}TIFF1:FileName_RBV
# XF:28ID1-BI{Cam:1}TIFF1:FileNumber
# XF:28ID1-BI{Cam:1}TIFF1:FileNumber_RBV
# XF:28ID1-BI{Cam:1}TIFF1:FilePath
# XF:28ID1-BI{Cam:1}TIFF1:FilePathExists_RBV
# XF:28ID1-BI{Cam:1}TIFF1:FilePath_RBV
# XF:28ID1-BI{Cam:1}TIFF1:FileTemplate
# XF:28ID1-BI{Cam:1}TIFF1:FileTemplate_RBV
# XF:28ID1-BI{Cam:1}TIFF1:FileWriteMode
# XF:28ID1-BI{Cam:1}TIFF1:FileWriteMode_RBV
# XF:28ID1-BI{Cam:1}TIFF1:FullFileName_RBV
# XF:28ID1-BI{Cam:1}TIFF1:LazyOpen
# XF:28ID1-BI{Cam:1}TIFF1:LazyOpen_RBV
# XF:28ID1-BI{Cam:1}TIFF1:MinCallbackTime
# XF:28ID1-BI{Cam:1}TIFF1:MinCallbackTime_RBV
# XF:28ID1-BI{Cam:1}TIFF1:NDArrayAddress
# XF:28ID1-BI{Cam:1}TIFF1:NDArrayAddress_RBV
# XF:28ID1-BI{Cam:1}TIFF1:NDArrayPort
# XF:28ID1-BI{Cam:1}TIFF1:NDArrayPort_RBV
# XF:28ID1-BI{Cam:1}TIFF1:NDimensions_RBV
# XF:28ID1-BI{Cam:1}TIFF1:NumCapture
# XF:28ID1-BI{Cam:1}TIFF1:NumCapture_RBV
# XF:28ID1-BI{Cam:1}TIFF1:NumCaptured_RBV
# XF:28ID1-BI{Cam:1}TIFF1:PluginType_RBV
# XF:28ID1-BI{Cam:1}TIFF1:PortName_RBV
# XF:28ID1-BI{Cam:1}TIFF1:ProcessPlugin
# XF:28ID1-BI{Cam:1}TIFF1:QueueFree
# XF:28ID1-BI{Cam:1}TIFF1:QueueSize
# XF:28ID1-BI{Cam:1}TIFF1:ReadFile
# XF:28ID1-BI{Cam:1}TIFF1:ReadFile_RBV
# XF:28ID1-BI{Cam:1}TIFF1:TempSuffix
# XF:28ID1-BI{Cam:1}TIFF1:TempSuffix_RBV
# XF:28ID1-BI{Cam:1}TIFF1:TimeStamp_RBV
# XF:28ID1-BI{Cam:1}TIFF1:UniqueId_RBV
# XF:28ID1-BI{Cam:1}TIFF1:WriteFile
# XF:28ID1-BI{Cam:1}TIFF1:WriteFile_RBV
# XF:28ID1-BI{Cam:1}TIFF1:WriteMessage
# XF:28ID1-BI{Cam:1}TIFF1:WriteStatus




# loc://DID_56AutoScale
# loc://DID_56AutoScale(2.0)
# loc://DID_56DispROI1
# loc://DID_56DispROI2
# loc://DID_56DispROI3
# loc://DID_56DispROI4
# loc://DID_56DispStats1
# loc://DID_56DispStats1(0)
# loc://DID_56DispStats2
# loc://DID_56DispStats2(0)
# loc://DID_56DispStats3
# loc://DID_56DispStats3(0)
# loc://DID_56DispStats4
# loc://DID_56DispStats4(0)
# loc://DID_56DispStats5
# loc://DID_56DispStats5(1)
# loc://DID_56Max
# loc://DID_56Max(65536)
# loc://DID_56Min
# loc://DID_56Min(0.0)
# loc://DID_56NSigma
# loc://DID_56NSigma(1.0)
# loc://DID_56hpx
# loc://DID_56hpy
# loc://DID_56vpx
# loc://DID_56vpy
file_loading_timer.stop()