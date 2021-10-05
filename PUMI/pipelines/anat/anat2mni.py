from PUMI.engine import AnatPipeline, QcPipeline
from PUMI.engine import NestedNode as Node
from PUMI.utils import get_reference, get_config, create_coregistration_qc
from nipype import Function
from nipype.interfaces import fsl


@QcPipeline(inputspec_fields=['in_file'],
            outputspec_fields=['out_file'])
def qc(wf, **kwargs):
    """

    Create quality check images for brain coregistration.

    Inputs
    ----------
    in_file (str): Path to the registered brain.

    Ouputs
    ----------
    out_file (str): Path to the quality check image

    Sinking
    ----------
    - The quality check image

    """
    plot = Node(Function(input_names=['registered_brain', 'template'],
                         output_names=['out_file'],
                         function=create_coregistration_qc),
                name='plot')
    wf.connect('inputspec', 'in_file', plot, 'registered_brain')
    plot.inputs.template = get_reference(wf, 'brain')

    # sinking
    wf.connect(plot, 'out_file', 'sinker', 'qc_anat2mni')

    # output
    wf.connect(plot, 'out_file', 'outputspec', 'out_file')


@AnatPipeline(inputspec_fields=['brain', 'head'],
              outputspec_fields=['output_brain', 'linear_xfm', 'inv_linear_xfm', 'nonlinear_xfm', 'inv_nonlinear_xfm',
                                 'std_template'])
def anat2mni_fsl(wf, **kwargs):
    # linear registration
    linear_reg = Node(interface=fsl.FLIRT(), name='linear_reg')
    linear_reg.inputs.cost = 'corratio'
    linear_reg.inputs.reference = get_reference(wf, 'brain')
    wf.connect('inputspec', 'brain', linear_reg, 'in_file')

    # calculate inverse of the flirt transformation matrix
    inv_linear_reg = Node(interface=fsl.utils.ConvertXFM(), name='inv_linear_reg')
    inv_linear_reg.inputs.invert_xfm = True
    wf.connect(linear_reg, 'out_matrix_file', inv_linear_reg, 'in_file')

    # non-linear registration
    nonlinear_reg = Node(interface=fsl.FNIRT(), name='nonlinear_reg')
    nonlinear_reg.inputs.ref_file = get_reference(wf, 'head')
    nonlinear_reg.inputs.refmask_file = get_reference(wf, 'brain_mask')
    nonlinear_reg.inputs.fieldcoeff_file = True
    nonlinear_reg.inputs.jacobian_file = True
    nonlinear_reg.config_file = get_config(wf, 'FSL', 'fnirt_config')
    wf.connect('inputspec', 'head', nonlinear_reg, 'in_file')
    wf.connect(linear_reg, 'out_matrix_file', nonlinear_reg, 'affine_file')

    # calculate inverse of the fnirt transformation matrix
    inv_nonlinear_reg = Node(interface=fsl.utils.InvWarp(), name="inv_nonlinear_reg")
    wf.connect('inputspec', 'brain', inv_nonlinear_reg, 'reference')
    wf.connect(nonlinear_reg, 'fieldcoeff_file', inv_nonlinear_reg, 'warp')

    # apply the results of FNIRT registration
    brain_warp = Node(interface=fsl.ApplyWarp(), name='brain_warp')
    brain_warp.inputs.ref_file = get_reference(wf, 'brain')
    wf.connect('inputspec', 'brain', brain_warp, 'in_file')
    wf.connect(nonlinear_reg, 'fieldcoeff_file', brain_warp, 'field_file')

    # QC
    anat2mni_qc = qc(name='anat2mni_fsl_qc', qc_dir=wf.qc_dir)
    wf.connect(brain_warp, 'out_file', anat2mni_qc, 'in_file')

    # sinking
    wf.connect(brain_warp, 'out_file', 'sinker', 'anat2mni_std')
    wf.connect(nonlinear_reg, 'fieldcoeff_file', 'sinker', 'anat2mni_warpfield')

    # outputs
    wf.get_node('outputspec').inputs.std_template = get_reference(wf, 'brain')
    wf.connect(linear_reg, 'out_matrix_file', 'outputspec', 'linear_xfm')
    wf.connect(inv_linear_reg, 'out_file', 'outputspec', 'inv_linear_xfm')
    wf.connect(nonlinear_reg, 'fieldcoeff_file', 'outputspec', 'nonlinear_xfm')
    wf.connect(nonlinear_reg, 'field_file', 'outputspec', 'field_file')
    wf.connect(inv_nonlinear_reg, 'inverse_warp', 'outputspec', 'inv_nonlinear_xfm')
    wf.connect(brain_warp, 'out_file', 'outputspec', 'output_brain')