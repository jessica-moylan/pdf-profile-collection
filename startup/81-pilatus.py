from ophyd import Component as Cpt
from ophyd import Signal

from ophyd import (SingleTrigger,
                   TIFFPlugin, ImagePlugin, DetectorBase,
                   HDF5Plugin, AreaDetector, EpicsSignal, EpicsSignalRO,
                   ROIPlugin, TransformPlugin, ProcessPlugin, PilatusDetector, 
		           PilatusDetectorCam, StatsPlugin)
from ophyd.areadetector.filestore_mixins import FileStoreTIFFIterativeWrite
from ophyd.areadetector import EpicsSignalWithRBV

from nslsii.ad33 import SingleTriggerV33, StatsPluginV33
from collections import OrderedDict
import uuid

file_loading_timer.start()


class TIFFPluginWithFileStore(TIFFPlugin, FileStoreTIFFIterativeWrite):
    def describe(self):
        ret = super().describe()
        key = self.parent._image_name
        color_mode = self.parent.cam.color_mode.get(as_string=True)

        if color_mode == "Mono":
            ret[key]["shape"] = [
                self.parent.cam.num_images.get(),
                self.array_size.height.get(),
                self.array_size.width.get()
            ]
        elif color_mode in ["RGB1", "Bayer"]:
            ret[key]["shape"] = [self.parent.cam.num_images.get(), *self.array_size.get()]
        else:
            raise RuntimeError(f"Should never be here, color mode {color_mode} not in "
                               f"['Mono', 'RGB1', 'Bayer']")

        cam_dtype = self.data_type.get(as_string=True)
        # print(f'\n{cam_dtype = }\n')

        type_map = {
            "UInt8": "|u1",
            "UInt16": "<u2",
            "Int32": "<i4",  # np.dtype('<i4') reports dtype('int32')
            "Float32": "<f4",
            "Float64": "<f8",
        }
        # print(f'\n{ret = }\n')

        if cam_dtype in type_map:
            ret[key].setdefault("dtype_str", type_map[cam_dtype])
            # ret[key].setdefault("dtype_numpy", type_map[cam_dtype])
            ret[key]["dtype_numpy"] = type_map[cam_dtype]

        # print(f'\n{ret = }\n')
        
        return ret
    
    def update_paths(self):
        base_path = f"/nsls2/data/pdf/proposals/{RE.md['cycle']}/{RE.md['data_session']}/assets/{self.parent.name}/%Y/%m/%d"
        self.write_path_template = base_path
        self.read_path_template = base_path

    def stage(self):
        self.update_paths()
        super().stage()


class PilatusDetectorCamV33(PilatusDetectorCam):
    wait_for_plugins = Cpt(EpicsSignal, 'WaitForPlugins',
                           string=True, kind='config')
    auto_increment = Cpt(EpicsSignal, 'AutoIncrement', string=True)
    file_name = Cpt(EpicsSignalWithRBV, 'FileName', string=True)
    next_file_num = Cpt(EpicsSignal, 'FileNumber')
    filename_format = Cpt(EpicsSignal, 'FileTemplate', string=True)
    file_path = Cpt(EpicsSignal, "FilePath", string=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs['wait_for_plugins'] = 'Yes'
        # self.stage_sigs['file_path'] = '/ramdisk/'
        # self.stage_sigs['file_format'] = 0
        # self.stage_sigs['auto_increment'] = 1
        # self.stage_sigs['next_file_num'] = 0
        # self.stage_sigs['filename_format'] = "%s%s_%6.6d.tiff"

    def ensure_nonblocking(self):
        self.stage_sigs['wait_for_plugins'] = 'Yes'
        for c in self.parent.component_names:
            cpt = getattr(self.parent, c)
            if cpt is self:
                continue
            if hasattr(cpt, 'ensure_nonblocking'):
                cpt.ensure_nonblocking()

    def stage(self):
        super().stage()
        self.file_name.set(str(uuid.uuid4()))
        # super().stage()


class PilatusV33(SingleTriggerV33, PilatusDetector):
    cam = Cpt(PilatusDetectorCamV33, 'cam1:')
    #stats1 = Cpt(StatsPluginV33, 'Stats1:')
    #stats2 = Cpt(StatsPluginV33, 'Stats2:')
    #stats3 = Cpt(StatsPluginV33, 'Stats3:')
    #stats4 = Cpt(StatsPluginV33, 'Stats4:')
    #stats5 = Cpt(StatsPluginV33, 'Stats5:')
    #roi1 = Cpt(ROIPlugin, 'ROI1:')
    #roi2 = Cpt(ROIPlugin, 'ROI2:')
    #roi3 = Cpt(ROIPlugin, 'ROI3:')
    #roi4 = Cpt(ROIPlugin, 'ROI4:')
    #proc1 = Cpt(ProcessPlugin, 'Proc1:')
    
    tiff = Cpt(TIFFPluginWithFileStore,
               suffix='TIFF1:',
               write_path_template='',
               root=f"/nsls2/data/pdf/proposals/{RE.md['cycle']}/{RE.md['data_session']}/assets", )
               ## CHL changed root on 2025/09/18 in order to be consistent with base path
    
    def set_exposure_time(self, exposure_time, verbosity=3):
        yield from bps.mv(self.cam.acquire_time, exposure_time, self.cam.acquire_period, exposure_time+.1)
        # self.cam.acquire_time.put(exposure_time)
        # self.cam.acquire_period.put(exposure_time+.1)
    
    def set_num_images(self, num_images):
        yield from bps.mv(self.cam.num_images, num_images)
        # self.cam.num_images = num_images


pilatus1 = PilatusV33('XF:28ID1-ES{Det:Pilatus}', name='pilatus-1')
# pilatus1.tiff.read_attrs = []
pilatus1.tiff.kind = 'normal'
pilatus1.tiff.update_paths()



#for looking at pilatus data

def show_me2(my_im, count_low=0, count_high=1, use_colorbar=False, use_cmap='viridis'):
    #my_low = np.percentile(my_im, per_low)
    #my_high = np.percentile(my_im, per_high)
    plt.imshow(my_im, vmin=count_low, vmax=count_high, cmap= use_cmap)
    if use_colorbar:
        plt.colorbar()



def show_me_db2(
    my_id,
    count_low=1,
    count_high=99,
    use_colorbar=False,
    dark_subtract=False,
    return_im=False,
    return_dark=False,
    new_db = True,
    use_cmap='viridis',
    suffix="_image",
):
    my_det_probably = db[my_id].start["detectors"][0] + suffix
    if new_db:
        my_im = (db[my_id].table(fill=True)[my_det_probably][1][0]).astype(float)
    else:
        my_im = (db[my_id].table(fill=True)[my_det_probably][1]).astype(float)

    if len(my_im) == 0:
        print("issue... passing")
        pass
    if dark_subtract:

        if "sc_dk_field_uid" in db[my_id].start.keys():
            my_dark_id = db[my_id].start["sc_dk_field_uid"]
            if new_db:
                dark_im = (db[my_dark_id].table(fill=True)[my_det_probably][1][0]).astype(float)
            else:
                dark_im = (db[my_dark_id].table(fill=True)[my_det_probably][1]).astype(float)
    
            my_im = my_im - dark_im
        else:
            print("this run has no associated dark")
    if return_im:
        return my_im
    if return_dark:
        return dark_im
    
    #if all else fails, plot!
    show_me2(my_im, count_low=count_low, count_high=count_high, use_colorbar=use_colorbar, use_cmap=use_cmap)


## Added by CHL 2025/09/19
def tqdm_sleep(rest_time, message='Sleep'):
    from tqdm import tqdm
    for j in tqdm(range(0,100), desc=message):
        time.sleep(rest_time/100)



####### convinence functions by Dan - 1/24/2023 ############
def set_Pilatus_energy_for_threshold(energy = 74.0):
    """ Default to energy = 74 (in keV), but can pass something else if you want """
    print ('setting Pilatus energy, please wait...')
    caput('XF:28ID1-ES{Det:Pilatus}cam1:Energy', energy)
    caput('XF:28ID1-ES{Det:Pilatus}cam1:ThresholdEnergy', energy/2)
    caput('XF:28ID1-ES{Det:Pilatus}cam1:ThresholdApply', 1)
    tqdm_sleep(8)

def reset_Pilatus_Power(delay=15.0):
    caput('XF:28ID1-ES{Det:Pilatus}cam1:ResetPowerTime', delay)
    t0=time.time()
    print ('performing Pilatus module power reset, please wait '+str(delay)+' seconds')
    caput('XF:28ID1-ES{Det:Pilatus}cam1:ResetPower', 1)
    tqdm_sleep(delay)
    print ('sleep time done, now waiting a bit more')
    tqdm_sleep(8)
    print ('coming back online, need another 20 seconds')
    tqdm_sleep(20)

def set_Pilatus_parameters(num_images=1, exposure_time=0.1):
    print ('setting number of images per collection to '+str(num_images))
    pilatus1.set_num_images(num_images)
    print ('setting exposure time for a single image to '+str(exposure_time))
    pilatus1.set_exposure_time(exposure_time)
    tqdm_sleep(1)




file_loading_timer.stop()