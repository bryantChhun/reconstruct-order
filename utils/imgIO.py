"""
Read and write Tiff in mManager format. Will be replaced by mManagerIO.py 
"""
import os
import numpy as np
import glob
import re
import cv2

def GetSubDirName(ImgPath):
    assert os.path.exists(ImgPath), 'Input folder does not exist!' 
    subDirPath = glob.glob(os.path.join(ImgPath, '*/'))    
    subDirName = [os.path.split(subdir[:-1])[1] for subdir in subDirPath]
#    assert subDirName, 'No sub directories found'
    return subDirName

def FindDirContainPos(ImgPath):
    """
    Recursively find the parent directory of "Pos#" directory
    """
    subDirName = GetSubDirName(ImgPath)
    assert subDirName, 'No "Pos" directories found. Check if the input folder contains "Pos"'
    subDir = subDirName[0]  # get pos0 if it exists
    ImgSubPath = os.path.join(ImgPath, subDir)
    if 'Pos' not in subDir:
        ImgPath = FindDirContainPos(ImgSubPath)
        return ImgPath
    else:
        return ImgPath
    
def process_position_list(img_obj_list, config):
    """
    Make sure all members of positions are part of io_obj.
    If positions = 'all', replace with actual list of positions
    """
    for idx, io_obj in enumerate(img_obj_list):
        config_pos_list = config.dataset.positions[idx]
        metadata_pos_list = io_obj.PosList
        if config_pos_list[0] == 'all':
            if isinstance(metadata_pos_list, list):
                pos_list = metadata_pos_list
            else:
                pos_list = [metadata_pos_list]
        else:
            assert all(i in metadata_pos_list for i in config_pos_list), \
            'Position list {} for sample in {} is invalid'.format(config_pos_list, io_obj.ImgSmPath)
            pos_list = config_pos_list
        
        img_obj_list[idx].PosList = pos_list
    return img_obj_list

def process_z_slice_list(img_obj_list, config):
    """
    Make sure all members of z_slices are part of io_obj.
    If z_slices = 'all', replace with actual list of z_slices
    """
    for idx, io_obj in enumerate(img_obj_list):
        config_z_list = config.dataset.z_slices[idx]
        metadata_z_list = range(io_obj.nZ)
        if config_z_list[0] == 'all':
            z_list = metadata_z_list
        else:
            assert all(i in metadata_z_list for i in config_z_list), \
            'Position list {} for sample in {} is invalid'.format(config_z_list, io_obj.ImgSmPath)
            z_list = config_z_list
        
        img_obj_list[idx].ZList = z_list
    return img_obj_list

def process_timepoint_list(img_obj_list, config):
    """
    Make sure all members of timepoints are part of io_obj.
    If timepoints = 'all', replace with actual list of timepoints
    """
    for idx, io_obj in enumerate(img_obj_list):
        config_t_list = config.dataset.timepoints[idx]
        metadata_t_list = range(io_obj.nTime)
        if config_t_list[0] == 'all':
            t_list = metadata_t_list
        else:
            assert all(i in metadata_t_list for i in config_t_list), \
            'Position list {} for sample in {} is invalid'.format(config_t_list, io_obj.ImgSmPath)
            t_list = config_t_list
        
        img_obj_list[idx].TimeList = t_list
    return img_obj_list


def loadTiff(acquDirPath, acquFiles):
    """
    Load single tiff file
    :param acquDirPath str: directory of the tiff
    :param acquFiles str: file name of the tiff
    :return 2D float32 array: image
    """
    TiffFile = os.path.join(acquDirPath, acquFiles)
    img = cv2.imread(TiffFile,-1) # flag -1 to preserve the bit dept of the raw image
    img = img.astype(np.float32, copy=False) # convert to float32 without making a copy to save memory
    # img = img.reshape(img.shape[0], img.shape[1],1)
    return img

def ParseFileList(acquDirPath):
    acquFiles = os.listdir(acquDirPath) 
    PolChan = []
    PolZ = []
    FluorChan = []
    FluorZ =[]
    for fileName in acquFiles:
        matchObjRaw = re.match( r'img_000000000_(State|PolAcquisition|Zyla_PolState)(\d+)( - Acquired Image|_Confocal40|_Widefield|)_(\d+).tif', fileName, re.M|re.I) # read images with "state" string in the filename
#        matchObjProc = re.match( r'img_000000000_(.*) - Computed Image_000.tif', fileName, re.M|re.I) # read computed images 
        matchObjFluor = re.match( r'img_000000000_Zyla_(Confocal40|Widefield|widefield)_(.*)_(\d+).tif', fileName, re.M|re.I) # read computed images 
        
        if matchObjRaw:                   
            PolChan += [matchObjRaw.group(2)]
            PolZ += [matchObjRaw.group(4)]        
        elif matchObjFluor:
            FluorChan += [matchObjFluor.group(1)]
            FluorZ += [matchObjFluor.group(2)]
        
            
    PolChan = list(set(PolChan))
    PolZ = list(set(PolZ))
    PolZ = [int(zIdx) for zIdx in PolZ]
    FluorChan = list(set(FluorChan))
    FluorZ = list(set(FluorZ))    
    return PolChan, PolZ, FluorChan, FluorZ
            
        
def ParseTiffInput_old(img_io):
    """
    Parse tiff file name following mManager/Polacquisition output format
    :param img_io instance: instance of mManagerIO class holding imaging metadata
    :return 3D float32 arrays: stack of images parsed based on their imaging modalities with axis order (channel, row,
    column)
    """
    acquDirPath = img_io.img_in_pos_path
    acquFiles = os.listdir(acquDirPath)
    ImgPol = []
    ImgProc = []
    ImgBF = []
    ImgFluor = np.zeros((4, img_io.height,img_io.width)) # assuming 4 flour channels for now
    tIdx = img_io.tIdx
    zIdx = img_io.zIdx
    for fileName in acquFiles: # load raw images with Sigma0, 1, 2, 3 states, and processed images        
        matchObjRaw = re.match( r'img_000000%03d_(State|PolAcquisition|Zyla_PolState|EMCCD_PolState)(\d+)( - Acquired Image|_Confocal40|_Widefield|)_%03d.tif'%(tIdx,zIdx), fileName, re.M|re.I) # read images with "state" string in the filename
        matchObjProc = re.match( r'img_000000%03d_(.*) - Computed Image_%03d.tif'%(tIdx,zIdx), fileName, re.M|re.I) # read computed images
        matchObjFluor1 = re.match(
            r'img_000000%03d_(Zyla|EMCCD)_(Confocal40|Widefield|widefield|BF)_(.*)_%03d.tif'%(tIdx,zIdx), fileName, re.M|re.I)
        matchObjFluor2 = re.match(
            r'img_000000%03d_(Zyla|EMCCD)_(.*)_(Confocal40|Widefield|widefield|BF)_%03d.tif' % (tIdx, zIdx), fileName,
            re.M | re.I)  # read computed images
        matchObjBF = re.match( r'img_000000%03d_(Zyla|EMCCD)_(BF)_%03d.tif'%(tIdx,zIdx), fileName, re.M|re.I) # read computed images
        if any([matchObjRaw, matchObjProc, matchObjFluor1, matchObjFluor2, matchObjBF]):
            img = loadTiff(acquDirPath, fileName)
            img -= img_io.blackLevel
            if matchObjRaw:
                ImgPol += [img]
            elif matchObjProc:
                ImgProc += [img]
            elif matchObjFluor1 or matchObjFluor2:
                if matchObjFluor1:
                    FluorChannName = matchObjFluor1.group(3)
                elif matchObjFluor2:
                    FluorChannName = matchObjFluor2.group(2)
                if FluorChannName in ['DAPI','405', '405nm']:
                    ImgFluor[0,:,:] = img
                elif FluorChannName in ['GFP','488', '488nm']:
                    ImgFluor[1,:,:] = img
                elif FluorChannName in ['TxR', 'TXR', '568', '568nm', '560']:
                    ImgFluor[2,:,:] = img
                elif FluorChannName in ['Cy5', 'IFP', '640', '640nm']:
                    ImgFluor[3,:,:] = img
            elif matchObjBF:
                ImgBF += [img]
    if ImgPol:
        ImgPol = np.stack(ImgPol)
    if ImgProc:
        ImgProc = np.stack(ImgProc)
    if ImgBF:
        ImgBF = np.stack(ImgBF)
    return ImgPol, ImgProc, ImgFluor, ImgBF

def parse_tiff_input(img_io):
    """
    Parse tiff file name following mManager/Polacquisition output format
    :param img_io instance: instance of mManagerIO class holding imaging metadata
    :return 3D float32 arrays: stack of images parsed based on their imaging modalities with axis order (channel, row,
    column)
    """
    acquDirPath = img_io.img_in_pos_path
    acquFiles = os.listdir(acquDirPath)
    ImgPol = np.zeros((4, img_io.height,img_io.width)) # pol channels has minimum 4 channels
    ImgProc = []
    ImgBF = []
    ImgFluor = np.zeros((4, img_io.height,img_io.width)) # assuming 4 flour channels for now
    tIdx = img_io.tIdx
    zIdx = img_io.zIdx
    for fileName in acquFiles: # load raw images with Sigma0, 1, 2, 3 states, and processed images
        matchObj = re.match( r'img_000000%03d_(.*)_%03d.tif'%(tIdx,zIdx), fileName, re.M|re.I) # read images with "state" string in the filename
        if matchObj:
            img = loadTiff(acquDirPath, fileName)
            img -= img_io.blackLevel
            if any(substring in matchObj.group(1) for substring in ['State', 'state', 'Pol']):
                if '0' in matchObj.group(1):
                    ImgPol[0, :, :] = img
                elif '1' in matchObj.group(1):
                    ImgPol[1, :, :] = img
                elif '2' in matchObj.group(1):
                    ImgPol[2, :, :] = img
                elif '3' in matchObj.group(1):
                    ImgPol[3, :, :] = img
                elif '4' in matchObj.group(1):
                    img = np.reshape(img, (1, img_io.height, img_io.width))
                    ImgPol = np.concatenate((ImgPol, img))
            elif any(substring in matchObj.group(1) for substring in ['Computed Image']):
                ImgProc += [img]
            elif any(substring in matchObj.group(1) for substring in
                     ['Confocal40','Confocal_40', 'Widefield', 'widefield', 'Fluor']):
                if any(substring in matchObj.group(1) for substring in ['DAPI', '405', '405nm']):
                    ImgFluor[0,:,:] = img
                elif any(substring in matchObj.group(1) for substring in ['GFP', '488', '488nm']):
                    ImgFluor[1,:,:] = img
                elif any(substring in matchObj.group(1) for substring in ['TxR', 'TXR', 'TX', '568', '561', '560']):
                    ImgFluor[2,:,:] = img
                elif any(substring in matchObj.group(1) for substring in ['Cy5', 'IFP', '640', '637']):
                    ImgFluor[3,:,:] = img
            elif any(substring in matchObj.group(1) for substring in ['BF']):
                ImgBF += [img]
    ImgPol = sort_pol_channels(ImgPol)
    if ImgProc:
        ImgProc = np.stack(ImgProc)
    if ImgBF:
        ImgBF = np.stack(ImgBF)
    return ImgPol, ImgProc, ImgFluor, ImgBF

def sort_pol_channels(img_pol):
    I_ext = img_pol[0, :, :]  # Sigma0 in Fig.2
    I_90 = img_pol[1, :, :]  # Sigma2 in Fig.2
    I_135 = img_pol[2, :, :]  # Sigma4 in Fig.2
    I_45 = img_pol[3, :, :]  # Sigma3 in Fig.2
    if img_pol.shape[0] == 4:  # if the images were taken using 4-frame scheme
        img_pol = np.stack((I_ext, I_45, I_90, I_135))  # order the channel following stokes calculus convention
    elif img_pol.shape[0] == 5:  # if the images were taken using 5-frame scheme
        I_0 = img_pol[4, :, :]
        img_pol = np.stack((I_ext, I_0, I_45, I_90, I_135))  # order the channel following stokes calculus convention
    return img_pol

def exportImg(img_io, imgDict):
    tIdx = img_io.tIdx
    zIdx = img_io.zIdx
    posIdx = img_io.posIdx
    output_path = img_io.img_out_pos_path
    for tiffName in img_io.chNamesOut:
        fileName = 'img_'+tiffName+'_t%03d_p%03d_z%03d.tif'%(tIdx, posIdx, zIdx)
        if len(imgDict[tiffName].shape)<3:
            cv2.imwrite(os.path.join(output_path, fileName), imgDict[tiffName])
        else:
            cv2.imwrite(os.path.join(output_path, fileName), cv2.cvtColor(imgDict[tiffName], cv2.COLOR_RGB2BGR))

