from nipype.algorithms import confounds
from nipype.interfaces import afni, fsl, utility
from PUMI.engine import NestedNode as Node, QcPipeline
from PUMI.engine import FuncPipeline


# Inputspec  is the input of the workflow
# Outputspec is the output of the workflow
from PUMI.pipelines.multimodal.image_manipulation import pick_volume, timecourse2png
from PUMI.utils import calc_friston_twenty_four, calculate_FD_Jenkinson, mean_from_txt, max_from_txt


@FuncPipeline(inputspec_fields=['in_file'],
              outputspec_fields=['out_file'])
def despiking_afni(wf, **kwargs):
    """
    todo
    """
    despike = Node(interface=afni.Despike(**kwargs), name='despike')
    despike.inputs.outputtype = 'NIFTI_GZ'
    wf.connect('inputspec', 'in_file', despike, 'in_file')
    wf.connect(despike, 'out_file', 'outputspec', 'out_file')

    #todo: qc


@QcPipeline(inputspec_fields=['func', 'motion_correction', 'plot_motion_trans', 'FD_figure'],
            outputspec_fields=[],
            default_regexp_sub=False,
            regexp_sub=[(r'(.*\/)([^\/]+)\/([^\/]+)\/([^\/]+)$', r'\g<1>qc_motion_correction/\g<3>-\g<2>.png'),
                        ('_subject_', 'sub-')])
def qc_motion_correction_mcflirt(wf, **kwargs):
    """

    Save quality check images for mcflirt motion-correction

    Inputs
    ----------
    func (str):
    motion_correction (str):
    plot_motion_trans (str):
    FD_figure (str):

    Outputs
    ----------

    Sinking
    ----------
    - rotations plot
    - translations plot
    - FD plot
    - timeseries

    """

    mc_timecourse = timecourse2png('mc_timeseries', sink=False)  # sink=False important for qc-folder-struktur
    wf.connect('inputspec', 'func', mc_timecourse, 'func')

    # sinking
    wf.connect(mc_timecourse, 'out_file', 'sinker', 'mc_timeseries')
    wf.connect('inputspec', 'motion_correction', 'sinker', 'mc_rotations')
    wf.connect('inputspec', 'plot_motion_trans', 'sinker', 'mc_translations')
    wf.connect('inputspec', 'FD_figure', 'sinker', 'FD')


@FuncPipeline(inputspec_fields=['in_file'],
              outputspec_fields=['func_out_file', 'mat_file', 'mc_par_file', 'friston24_file', 'FD_file'])
def motion_correction_mcflirt(wf, reference_vol='middle', FD_mode='Power', **kwargs):
    """

    Use FSL MCFLIRT to do the motion correction of the 4D functional data and use the 6df rigid body motion parameters
    to calculate friston24 parameters for later nuissance regression step.

    Parameters
    ----------
    reference_vol (str): Either "first", "middle", "last", "mean", or the index of the volume which the rigid body
                         registration (motion correction) will use as reference.
                         Default is 'middle'.
    FD_mode: Either "Power" or "Jenkinson"

    Inputs
    ----------
    in_file (str): Reoriented functional file

    Outputs
    ----------
    func_out_file (str): Path to motion-corrected timeseries
    mat_file (str): Path to motion-correction transformation matrices
    mc_par_file (str): Path to file with motion parameters
    friston24_file (str): Path to file with friston24 parameters
    FD_file (str): Path to file with FD

    Sinking
    ----------
    - motion-corrected timeseries
    - motion-correction transformation matrices
    - absolute and relative displacement parameters
    - friston24 parameters
    - FD
    - FDmax
    - quality check images (FD/rotations/translations and timeseries plot)

    Acknowledgements
    ----------
    Adapted from Balint Kincses (2018)

    Modified version of PAC.func_preproc.func_preproc
    (https://github.com/FCP-INDI/C-PAC/blob/main/CPAC/func_preproc/func_preproc.py)
    and CPAC.generate_motion_statistics.generate_motion_statistics
    (https://github.com/FCP-INDI/C-PAC/blob/main/CPAC/generate_motion_statistics/generate_motion_statistics.py)
    """

    if FD_mode not in ['Power', 'Jenkinson']:
        raise ValueError(f'FD_mode has to be "Power" or "Jenkinson"! %s is not a valid option!' % FD_mode)

    refvol = pick_volume(volume=reference_vol, name='refvol')
    wf.connect('inputspec', 'in_file', refvol, 'in_file')

    mcflirt = Node(interface=fsl.MCFLIRT(interpolation="spline", stats_imgs=False), name='mcflirt')
    if reference_vol == "mean":
        mcflirt.inputs.mean_vol = True
    mcflirt.inputs.dof = 6
    mcflirt.inputs.save_mats = True
    mcflirt.inputs.save_plots = True
    mcflirt.inputs.save_rms = True
    mcflirt.inputs.stats_imgs = False
    wf.connect('inputspec', 'in_file', mcflirt, 'in_file')
    if reference_vol != "mean":
        wf.connect(refvol, 'out_file', mcflirt, 'ref_file')

    calc_friston = Node(
        utility.Function(
            input_names=['in_file'], output_names=['out_file'],
            function=calc_friston_twenty_four
        ),
        name='calc_friston'
    )
    wf.connect(mcflirt, 'par_file', calc_friston, 'in_file')

    if FD_mode == "Power":
        calculate_FD = Node(
            confounds.FramewiseDisplacement(
                parameter_source='FSL',
                save_plot=True,
                out_figure='fd_power_2012.png'
            ),
            name='calculate_FD_Power'
        )
    elif FD_mode == "Jenkinson":
        calculate_FD = Node(
            utility.Function(
                input_names=['in_file'],
                output_names=['out_file'],
                function=calculate_FD_Jenkinson
            ),
            name='calculate_FD_Jenkinson'
        )
    wf.connect(mcflirt, 'par_file', calculate_FD, 'in_file')

    mean_FD = Node(
        utility.Function(
            input_names=['in_file', 'axis', 'header', 'out_file'],
            output_names=['mean_file'],
            function=mean_from_txt
        ),
        name='meanFD'
    )
    mean_FD.inputs.axis = 0  # global mean
    mean_FD.inputs.header = True  # global mean
    mean_FD.inputs.out_file = 'FD.txt'
    wf.connect(calculate_FD, 'out_file', mean_FD, 'in_file')

    max_FD = Node(
        utility.Function(
            input_names=['in_file', 'axis', 'header', 'out_file'],
            output_names=['max_file'],
            function=max_from_txt
        ),
        name='maxFD'
    )
    max_FD.inputs.axis = 0  # global mean
    max_FD.inputs.header = True
    max_FD.inputs.out_file = 'FDmax.txt'
    wf.connect(calculate_FD, 'out_file', max_FD, 'in_file')

    plot_motion_rot = Node(
        interface=fsl.PlotMotionParams(in_source='fsl'),
        name='plot_motion_rot')
    plot_motion_rot.inputs.plot_type = 'rotations'
    wf.connect(mcflirt, 'par_file', plot_motion_rot, 'in_file')

    plot_motion_trans = Node(
        interface=fsl.PlotMotionParams(in_source='fsl'),
        name='plot_motion_trans')
    plot_motion_trans.inputs.plot_type = 'translations'
    wf.connect(mcflirt, 'par_file', plot_motion_trans, 'in_file')

    qc_mc = qc_motion_correction_mcflirt('qc_mc')
    wf.connect(plot_motion_rot, 'out_file', qc_mc, 'motion_correction')
    wf.connect(plot_motion_trans, 'out_file', qc_mc, 'plot_motion_trans')
    wf.connect(calculate_FD, 'out_figure', qc_mc, 'FD_figure')
    wf.connect(mcflirt, 'out_file', qc_mc, 'func')

    # sinking
    wf.connect(mcflirt, 'out_file', 'sinker', 'mc_func')
    wf.connect(mcflirt, 'par_file', 'sinker', 'mc_par')
    wf.connect(mcflirt, 'rms_files', 'sinker', 'mc_rms')
    wf.connect(calc_friston, 'out_file', 'sinker', 'mc_first24')
    wf.connect(mean_FD, 'mean_file', 'sinker', 'FD')
    wf.connect(max_FD, 'max_file', 'sinker', 'FDmax')

    # output
    wf.connect(mcflirt, 'out_file', 'outputspec', 'func_out_file')
    wf.connect(mcflirt, 'mat_file', 'outputspec', 'mat_file')
    wf.connect(mcflirt, 'par_file', 'outputspec', 'mc_par_file')
    wf.connect(calculate_FD, 'out_file', 'outputspec', 'FD_file')
    wf.connect(calc_friston, 'out_file', 'outputspec', 'friston24_file')




