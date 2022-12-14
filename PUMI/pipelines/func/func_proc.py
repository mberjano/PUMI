from PUMI.engine import FuncPipeline, NestedNode as Node
from nipype.interfaces import fsl, afni
from PUMI.pipelines.anat.segmentation import bet_fsl
from PUMI.pipelines.func.compcor import compcor
from PUMI.pipelines.func.concat import concat
from PUMI.pipelines.func.data_censorer import datacens_workflow_threshold
from PUMI.pipelines.func.deconfound import motion_correction_mcflirt, nuisance_removal
from PUMI.pipelines.func.temporal_filtering import temporal_filtering


@FuncPipeline(inputspec_fields=['func', 'cc_noise_roi'],
              outputspec_fields=['func_preprocessed', 'func_preprocessed_scrubbed', 'FD'])
def func_proc_despike_afni(wf, stdrefvol='middle', fwhm=0, carpet_plot='', **kwargs):

    """
    Performs processing of functional (resting-state) images:
    Images should be already reoriented, e.g. with fsl fslreorient2std (see scripts/ex_pipeline.py)
    Workflow inputs:
        :param func: The functional image file.

    Tamas Spisak
    tamas.spisak@uk-essen.de
    2018
        """

    # ToDo: Add fmri2QC
    # ToDo: Redo documentation
    # ToDo: check if variable names and node names are the same

    mybet = bet_fsl('mybet', fmri=True)
    wf.connect('inputspec', 'func', mybet, 'in_file')

    mymc = motion_correction_mcflirt('mymc', reference_vol=stdrefvol)
    wf.connect(mybet, 'out_file', mymc, 'in_file')

    if carpet_plot:
        add_masks = Node(fsl.ImageMaths(op_string=' -add'), name="addimgs")
        wf.connect('inputspec', 'cc_noise_roi', add_masks, 'in_file')
        wf.connect(mybet, 'brain_mask', add_masks, 'in_file2')

    mydespike = Node(afni.Despike(outputtype="NIFTI_GZ"), name="DeSpike")
    wf.connect(mymc, 'func_out_file', mydespike, 'in_file')

    mycmpcor = compcor('mycmpcor') # to  WM+CSF signal
    wf.connect(mydespike, 'out_file', mycmpcor, 'func_aligned')
    wf.connect('inputspec', 'cc_noise_roi', mycmpcor, 'mask_file')

    myconc = concat('myconc')
    wf.connect(mycmpcor, 'out_file', myconc, 'par1')
    wf.connect(mymc, 'friston24_file', myconc, 'par2')

    mynuisscor = nuisance_removal('mynuisscor') # regress out 5 compcor variables and the Friston24
    wf.connect(myconc, 'concat_file', mynuisscor, 'design_file')
    wf.connect(mydespike, 'out_file', mynuisscor, 'in_file')

    # optional smoother:
    if fwhm > 0:
        smoother = Node(interface=fsl.Smooth(fwhm=fwhm), name="smoother")
        wf.connect(mynuisscor, 'out_file', smoother, 'in_file')

    mytmpfilt = temporal_filtering('mytmpfilt')
    mytmpfilt.get_node('inputspec').inputs.highpass = 0.008
    mytmpfilt.get_node('inputspec').inputs.lowpass = 0.08
    if fwhm > 0:
        wf.connect(smoother, 'smoothed_file', mytmpfilt, 'func')
    else:
        wf.connect(mynuisscor, 'out_file', mytmpfilt, 'func')

    myscrub = datacens_workflow_threshold('myscrub', ex_before=0, ex_after=0)
    wf.connect(mymc, 'FD_file', myscrub, 'FD')
    wf.connect(mytmpfilt, 'out_file', myscrub, 'func')

    # output
    wf.connect(mymc, 'FD_file', 'outputspec', 'FD')
    wf.connect(myscrub, 'scrubbed_image', 'outputspec', 'func_preprocessed_scrubbed')
    wf.connect(mytmpfilt, 'out_file', 'outputspec', 'func_preprocessed')

