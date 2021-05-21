from nipype import Node, IdentityInterface, Workflow, DataSink, Function
from nipype.interfaces import BIDSDataGrabber
from nipype.utils.filemanip import list_to_filename
import PUMI.pipelines.anat.Better_bckp as bet
import os

# experiment specific parameters:
# paths relative to PUMI directory not PUMI/scripts
input_dir = 'data_in/example-bids'  # place where the bids data is located
output_dir = 'data_out'  # place where the folder 'BET' will be created for the results of this script
working_dir = 'data_out'  # place where the folder 'bet_iter_wf' will be created for the workflow

subjects = ['001', '002', '003']  # subjects for which a brain extraction should be performed
# ---


# Change current working directory to PUMI, if necessary
if os.getcwd().find('/PUMI/examples') != -1:
    os.chdir('..')

# Step 1: Create a subroutine (subgraph) for every subject
inputspec = Node(IdentityInterface(fields=['subject']), name='input_node')
inputspec.iterables = [('subject', subjects)]

# Step 2: Get anatomical images
bids_grabber = Node(BIDSDataGrabber(), name='bids_grabber')
bids_grabber.inputs.base_dir = os.path.abspath(input_dir)
bids_grabber.inputs.output_query = {
    'T1w': dict(
        subject=subjects,
        datatype='anat',
        extension=['nii', 'nii.gz']
    )
}

# Step 3: 'Unpack' list from bids_grabber
# bids_grabber returns a list with a string (path to the anat image of a subject),
# but fsl.Bet does not take a list as a input file
path_extractor = Node(
    Function(
        input_names=["filelist"],
        output_names=["out_file"],
        function=list_to_filename
    ),
    name="path_extractor_node"
)

# Step 4: Do the brain extraction
bet_wf = bet.bet_workflow()

# Step 5: Save results
sinker = Node(DataSink(), name='sinker')
sinker.inputs.base_directory = os.path.abspath(output_dir)
sinker.inputs.substitutions = [('_subject_', 'bet-subject-')]

# Step 6: Start workflow
wf = Workflow(name='bet_iter_wf')
wf.base_dir = os.path.abspath(working_dir)
wf.connect([
    (inputspec, bids_grabber, [('subject', 'subject')]),
    (bids_grabber, path_extractor, [('T1w', 'filelist')]),
    (path_extractor, bet_wf, [('out_file', 'inputspec.in_file')]),
    (bet_wf, sinker, [('outputspec.brain', 'BET')])
])
wf.run()
