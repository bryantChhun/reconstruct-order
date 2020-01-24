"""
Class to read mManager format images saved separately and their metadata (JSON) .
"""
import json, os, fnmatch
import numpy as np
import pandas as pd
import cv2
from ..utils.imgIO import get_sub_dirs, get_sorted_names
from ..metadata.MicromanagerMetadata import mm1_meta_parser, mm2_beta_meta_parser, mm2_gamma_meta_parser

"""
mManagerReader:
- Represents a single Sample as defined by the "samples" field in the configfile
- A single Sample can contain:
    - multiple positions, channels, timepoints, z slices
    
1 mManagerReader maintains lists of folders or paths (?) referring to all the above
2 mManagerReader stores parsed metadata from the acquisition's outputted metadata.txt file
3 mManagerReader maintains some (?) ConfigReader parameters relevant to processing such as:
    - output_chan
    - bg_correct
    - bg_method
4 as image processing advances, attributes within mManagerReader are adjusted to reflect the state of image processing:
    - for example, during coordinate looping, the self.t_idx, self.z_idx etc.. are incremented

1-3 describe a highly static nature of mManagerReader
4 describes a highly stateful nature of mManagerReader

"""
#Todo: for often adjusted attributes, create property setters/getters
#todo: consider for "final" attributes, should we use property setter/getters to "lock" the values?


class mManagerReader(object):
    """
    General mManager metadata and image reader for data saved as separate 2D tiff files

    Parameters
    ----------
    img_sample_path : str
        full path of the acquisition folder (parent folder of pos folder)
    img_output_path : str
        full path of the output folder
    input_chan : list
        list of input channel names
    output_chan : list
        list of output channel names

    Attributes
    ----------
    input_meta_file : dict
        input mManager meta file of the acquistion
    _meta_pos_list : list
        position list in the meta file
    _pos_list : list
        position list to process
    name : str
        acquisition folder name
    output_meta_file : dict
        output meta file
    img_sm_path : str
        path of the acquisition folder
    img_in_pos_path : str
        path of the current position folder
    img_output_path : str
        full path of the output folder
    width : int
        width of the input image
    height : int
        height of the input image
    channels : list
        channels in the meta file
    input_chans : list
        channels to read
    n_input_chans : int
        number of channels to read
    output_chans : list
        output channels
    n_output_chans : int
        number of output channels
    n_pos : int
        number of positions in the meta file
    n_time : int
        number of time points in the meta file
    n_z :
        number of time slices in the meta file
    size_x_um : float
        pixel size in x
    size_y_um : float
        pixel size in y
    size_z_um : float
        z step
    time_stamp : list
        time points in the meta file
    pos_idx : int
        current postion index to process
    t_idx : int
        current time index to process
    z_idx : int
        current z index to process
    bg : str
        background folder name
    bg_method : str
        "Global" or "Local". Type of background correction. "Global" will correct each image
         using the same background. "Local" will do correction with locally estimated
         background in addition to global background
    bg_correct : bool
        Perform background correct (True) or not (False)
    binning : int
        binning (or pooling) size for the images

    """

    def __init__(self, img_sample_path, img_output_path=None, input_chans=[], output_chans=[], binning=1):
        self._pos_list = None
        pos_path = img_sample_path # mManager 2.0 single position format
        sub_dirs = get_sub_dirs(img_sample_path)
        if sub_dirs:
            sub_dir = sub_dirs[0] # pos0
            # mManager 1.4.22
            if 'Pos' in sub_dir:
                pos_path = os.path.join(img_sample_path, sub_dir)
            # mManager 2.0 single position format
            elif len(sub_dirs) == 1 and sub_dirs[0] == 'Default':
                """
                Single position data does not produce a "position list" from the metadata
                We can assign it here
                """
                pos_path = os.path.join(img_sample_path, sub_dir)
                self._pos_list = [sub_dirs[0]]
            else:
                pos_path = os.path.join(img_sample_path, sub_dir)
        print(f"SAMPLE PATH = {pos_path}")

        metadata_path = os.path.join(pos_path, 'metadata.txt')
        with open(metadata_path, 'r') as f:
            self.input_meta_file = json.load(f)

        self.mm_version = self.input_meta_file['Summary']['MicroManagerVersion']
        print(f"\tMM VERSION = {self.mm_version}")

        # get version specific information
        #   position list, image width and height
        if '1.4.22' in self.mm_version:
            self._meta_pos_list, self.width, self.height, self.time_stamp = mm1_meta_parser(self.input_meta_file)
            if self._pos_list is None:
                self._pos_list = self._meta_pos_list

        elif 'beta' in self.mm_version:
            self._meta_pos_list, self.width, self.height, self.time_stamp = mm2_beta_meta_parser(self.input_meta_file)
            if self._pos_list is None:
                self._pos_list = self._meta_pos_list

        elif 'gamma' in self.mm_version:
            self._meta_pos_list, self.width, self.height, self.time_stamp = mm2_gamma_meta_parser(self.input_meta_file)
            if self._pos_list is None:
                self._pos_list = self._meta_pos_list

        else:
            raise ValueError(
                'Current MicroManager reader only supports version 1.4.22 and 2.0 but {} was detected'.
                    format(self.mm_version))

        self.img_sm_path = img_sample_path
        self.img_in_pos_path = pos_path
        self.img_names = get_sorted_names(pos_path)
        self.img_name_format = None
        self._detect_img_name_format()
        self.img_output_path = img_output_path
        self.input_chans = self.channels = self.input_meta_file['Summary']['ChNames']
        if input_chans:
            self.input_chans = input_chans
        self.n_input_chans = len(input_chans)
        self.output_chans = output_chans  # output channel names
        self.n_output_chans = len(output_chans)
        self.output_meta_file = []
        self.binning = binning
        self.name = self.input_meta_file["Summary"]["Prefix"]
        self.n_pos = self.input_meta_file['Summary']['Positions']
        self.n_time = self.input_meta_file['Summary']['Frames']
        self.n_z = self.input_meta_file['Summary']['Slices']
        self._t_list = self._meta_t_list = list(range(0, self.n_time))
        self._z_list = self._meta_z_list = list(range(0, self.n_z))
        self.size_z_um = self.input_meta_file['Summary']['z-step_um']
        self.pos_idx = 0  # assuming only single image for background
        self.t_idx = 0
        self.z_idx = 0
        self.chan_idx = 0
        self.bg = 'No Background'
        self.bg_method = 'Global'
        self.bg_correct = True

    @property
    def pos_list(self):
        return self._pos_list

    @pos_list.setter
    def pos_list(self, value):
        """position list to process

        Parameters
        ----------
        value: list
        position list to process

        """
        assert set(value).issubset(self._meta_pos_list), \
            'some positions cannot be found in metadata'
        self._pos_list = value

    @property
    def t_list(self):
        return self._t_list

    @t_list.setter
    def t_list(self, value):
        """time list to process

        Parameters
        ----------
        value: list
        time list to process

        """
        assert set(value).issubset(self._meta_t_list), \
            'some positions cannot be found in metadata'
        self._t_list = value

    @property
    def z_list(self):
        return self._z_list

    @z_list.setter
    def z_list(self, value):
        """z list to process

        Parameters
        ----------
        value: list
        z list to process

        """
        assert set(value).issubset(self._meta_z_list), \
            'some positions cannot be found in metadata'
        self._z_list = value

    def _detect_img_name_format(self):
        # *Bryant 1-21-2020: we will use the same convention as in the constructor to identify micro-manager format
        #   will no longer use string parsing to ID mm format

        img_name = self.img_names[0]

        # if 'img_000000' in img_name:
        #     self.img_name_format = 'mm_1_4_22'
        # elif 'position' in img_name:
        #     self.img_name_format = 'mm_2_0'
        # elif 'img_' in img_name:
        #     self.img_name_format = 'recon_order'
        # else:
        #     raise ValueError('Unknown image name format')

        if '1.4.22' in self.mm_version:
            self.img_name_format = 'mm_1_4_22'
        elif 'beta' in self.mm_version:
            self.img_name_format = 'mm_2_0'
        elif 'gamma' in self.mm_version:
            self.img_name_format = 'mm_2_0'
        elif 'img_' in img_name:
            self.img_name_format = 'recon_order'
        else:
            raise ValueError("Unknown image name format")

    def get_chan_name(self):
        return self.input_chans[self.chan_idx]

    def get_img_name(self):
        """
        mm2.0 file names contain position index that does not obviously map to the position list folder name
            therefore, we have to do a search for matching strings based on parameters Channel, Time, Z

        :return: string: image name
        """
        img_name = None

        if self.img_name_format == 'mm_1_4_22':
            img_name = 'img_000000{:03d}_{}_{:03d}.tif'.\
                format(self.t_idx, self.get_chan_name(), self.z_idx)

        elif self.img_name_format == 'mm_2_0':
            chan_meta_idx = self.channels.index(self.get_chan_name())

            # could do binary search but might have to parameterize the list because list is str
            for file in sorted(os.listdir(self.img_in_pos_path)):
                if fnmatch.fnmatch(file, 'img_channel{:03d}_position*_time{:09d}_z{:03d}.tif'.format(
                        chan_meta_idx, self.t_idx, self.z_idx)):
                    img_name = file
                    print("\t\tFOUND FNMATCH, file = "+img_name)

            if img_name is None:
                img_name = 'img_channel{:03d}_position{:03d}_time{:09d}_z{:03d}.tif'. \
                    format(chan_meta_idx, self.pos_idx, self.t_idx, self.z_idx)
                print("\t\tNO FNMATCH, Guessing file name = " + img_name)

        elif self.img_name_format == 'recon_order':
            img_name = 'img_{}_t{:03d}_p{:03d}_z{:03d}.tif'.\
                format(self.t_idx, self.pos_idx, self.z_idx, self.get_chan_name())

        else:
            raise ValueError('Undefined image name format')
        return img_name

    def read_img(self):
        """read a single image at (c,t,p,z)"""
        img_name = self.get_img_name()
        img_file = os.path.join(self.img_in_pos_path, img_name)
        img = cv2.imread(img_file, -1) # flag -1 to preserve the bit dept of the raw image
        img = img.astype(np.float32, copy=False)  # convert to float32 without making a copy to save memory
        return img

    def read_multi_chan_img_stack(self, z_range=None):
        """read multi-channel image stack at a given (t,p)"""
        if not os.path.exists(self.img_sm_path):
            raise FileNotFoundError(
                "image file doesn't exist at:", self.img_sm_path
            )
        if not z_range:
            z_range = [0, self.nZ]
        img_chann = []  # list of 2D or 3D images from different channels
        for chan_idx in range(self.n_input_chans):
            img_stack = []
            self.chan_idx = chan_idx
            for z_idx in range(z_range[0], z_range[1]):
                self.z_idx = z_idx
                img = self.read_img()
                img_stack += [img]
            img_stack = np.stack(img_stack)  # follow zyx order
            img_chann += [img_stack]
        return img_chann
    
    def write_img(self, img):
        """only supports recon_order image name format currently"""
        if not os.path.exists(self.img_output_path): # create folder for processed images
            os.makedirs(self.img_output_path)
        img_name = 'img_'+self.output_chans[self.chan_idx]+'_t%03d_p%03d_z%03d.tif'%(self.t_idx, self.pos_idx, self.z_idx)
        if len(img.shape)<3:
            cv2.imwrite(os.path.join(self.img_output_path, img_name), img)
        else:
            cv2.imwrite(os.path.join(self.img_output_path, img_name), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            
    def writeMetaData(self):
        if not os.path.exists(self.img_output_path): # create folder for processed images
            os.makedirs(self.img_output_path)
        self.input_meta_file['Summary']['ChNames'] = self.input_chans
        self.input_meta_file['Summary']['Channels'] = self.n_input_chans
        metaFileName = os.path.join(self.img_output_path, 'metadata.txt')
        with open(metaFileName, 'w') as f:  
            json.dump(self.input_meta_file, f)
        df_pos_path = os.path.join(self.img_output_path, 'pos_table.csv')
        df_pos = pd.DataFrame(list(enumerate(self.pos_list)),
                          columns=['pos idx', 'pos dir'])
        df_pos.to_csv(df_pos_path, sep=',')


class PolAcquReader(mManagerReader):
    """PolAcquistion mManager metadata and image reader
    Parameters
    ----------
    mManagerReader : class
        General mManager metadata and image reader for data saved as separate 2D tiff files

    Attributes
    ----------
    acquScheme : str
        Pol images acquiring schemes. '4-Frame' or '5-Frame'
    bg : str
        background folder name in metadata
    blackLevel : int
        black level of the camera
    mirror : str
        'Yes' or 'No'. Changing this flag will flip the slow axis horizontally
    swing : float
        swing of the elliptical polarization states in unit of fraction of wavelength
    wavelength : int
        wavelenhth of the illumination light (nm)


    """
    def __init__(self, img_sample_path, img_output_path=None, input_chans=[], output_chans=[], binning=1):

        mManagerReader.__init__(self, img_sample_path, img_output_path, input_chans, output_chans, binning)
        metaFile = self.input_meta_file
        self.acquScheme = metaFile['Summary']['~ Acquired Using']
        self.bg = metaFile['Summary']['~ Background']
        self.blackLevel = metaFile['Summary']['~ BlackLevel']
        self.mirror = metaFile['Summary']['~ Mirror']
        self.swing = metaFile['Summary']['~ Swing (fraction)']
        self.wavelength = metaFile['Summary']['~ Wavelength (nm)']

