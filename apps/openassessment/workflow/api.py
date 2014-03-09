"""
Public interface for the Assessment Workflow.

"""
import copy
import logging

from django.db import DatabaseError


from submissions import api as sub_api
from .models import AssessmentWorkflow
from .serializers import AssessmentWorkflowSerializer

logger = logging.getLogger(__name__)


class AssessmentWorkflowError(Exception):
    """An error that occurs during workflow actions.

    This error is raised when the Workflow API cannot perform a requested
    action.

    """
    pass


class AssessmentWorkflowInternalError(AssessmentWorkflowError):
    """An error internal to the Workflow API has occurred.

    This error is raised when an error occurs that is not caused by incorrect
    use of the API, but rather internal implementation of the underlying
    services.

    """
    pass


class AssessmentWorkflowRequestError(AssessmentWorkflowError):
    """This error is raised when there was a request-specific error

    This error is reserved for problems specific to the use of the API.

    """

    def __init__(self, field_errors):
        Exception.__init__(self, repr(field_errors))
        self.field_errors = copy.deepcopy(field_errors)


class AssessmentWorkflowNotFoundError(AssessmentWorkflowError):
    """This error is raised when no submission is found for the request.

    If a state is specified in a call to the API that results in no matching
    Submissions, this error may be raised.

    """
    pass


def create_workflow(submission_uuid):
    """Begins a new assessment workflow.

    Create a new workflow that other assessments will record themselves against.

    Args:
        submission_uuid (str): The UUID for the submission that all our
            assessments will be evaluating.

    Returns:
        dict: Assessment workflow information containing the keys
            `submission_uuid`, `uuid`, `status`, `created`, `modified`

    Raises:
        AssessmentWorkflowRequestError: If the `submission_uuid` passed in does
            not exist or is of an invalid type.
        AssessmentWorkflowInternalError: Unexpected internal error, such as the
            submissions app not being available or a database configuation
            problem.

    Examples:
        >>> create_assessment_workflow('e12bd3ee-9fb0-11e3-9f68-040ccee02800')
        {
            'submission_uuid': u'e12bd3ee-9fb0-11e3-9f68-040ccee02800',
            'uuid': u'e12ef27a-9fb0-11e3-aad4-040ccee02800',
            'status': u'peer',
            'created': datetime.datetime(2014, 2, 27, 13, 12, 59, 225359, tzinfo=<UTC>),
            'modified': datetime.datetime(2014, 2, 27, 13, 12, 59, 225675, tzinfo=<UTC>)
        }
    """
    def sub_err_msg(specific_err_msg):
        return (
            u"Could not create assessment workflow: "
            u"retrieving submission {} failed: {}"
            .format(submission_uuid, specific_err_msg)
        )

    try:
        submission_dict = sub_api.get_submission(submission_uuid)
    except sub_api.SubmissionNotFoundError as err:
        err_msg = sub_err_msg("submission not found")
        logger.error(err_msg)
        raise AssessmentWorkflowRequestError(err_msg)
    except sub_api.SubmissionRequestError as err:
        err_msg = sub_err_msg(err)
        logger.error(err_msg)
        raise AssessmentWorkflowRequestError(err_msg)
    except sub_api.SubmissionInternalError as err:
        err_msg = sub_err_msg(err)
        logger.error(err)
        raise AssessmentWorkflowInternalError(
            u"retrieving submission {} failed with unknown error: {}"
            .format(submission_uuid, err)
        )

    # We're not using a serializer to deserialize this because the only variable
    # we're getting from the outside is the submission_uuid, which is already
    # validated by this point.
    try:
        workflow = AssessmentWorkflow.objects.create(
            submission_uuid=submission_uuid,
            status=AssessmentWorkflow.STATUS.peer
        )
    except DatabaseError as err:
        err_msg = u"Could not create assessment workflow: {}".format(err)
        logger.exception(err_msg)
        raise AssessmentWorkflowInternalError(err_msg)

    return AssessmentWorkflowSerializer(workflow).data


def get_workflow_for_submission(submission_uuid, assessment_requirements):
    """Returns Assessment Workflow information

    This will implicitly call `update_from_assessments()` to make sure we
    give the most current information.

    Args:
        student_item_dict (dict):
        submission_uuid (str):

    Returns:
        dict: Assessment workflow information containing the keys
            `submission_uuid`, `uuid`, `status`, `created`, `modified`

    Raises:
        AssessmentWorkflowRequestError: If the `workflow_uuid` passed in is not
            a string type.
        AssessmentWorkflowNotFoundError: No assessment workflow matching the
            requested UUID exists.
        AssessmentWorkflowInternalError: Unexpected internal error, such as the
            submissions app not being available or a database configuation
            problem.

    Examples:
        >>> get_assessment_workflow('e12ef27a-9fb0-11e3-aad4-040ccee02800')
        {
            'submission_uuid': u'e12bd3ee-9fb0-11e3-9f68-040ccee02800',
            'uuid': u'e12ef27a-9fb0-11e3-aad4-040ccee02800',
            'status': u'peer',
            'created': datetime.datetime(2014, 2, 27, 13, 12, 59, 225359, tzinfo=<UTC>),
            'modified': datetime.datetime(2014, 2, 27, 13, 12, 59, 225675, tzinfo=<UTC>)
        }

    """
    return update_from_assessments(submission_uuid, assessment_requirements)


def update_from_assessments(submission_uuid, assessment_requirements):
    workflow = _get_workflow_model(submission_uuid)
    workflow.update_from_assessments(assessment_requirements)
    return _serialized_with_details(workflow, assessment_requirements)


def _get_workflow_model(submission_uuid):
    if not isinstance(submission_uuid, basestring):
        raise AssessmentWorkflowRequestError("submission_uuid must be a string type")

    try:
        workflow = AssessmentWorkflow.objects.get(submission_uuid=submission_uuid)
    except AssessmentWorkflow.DoesNotExist:
        raise AssessmentWorkflowNotFoundError(
            u"No assessment workflow matching submission_uuid {}".format(submission_uuid)
        )
    except Exception as exc:
        # Something very unexpected has just happened (like DB misconfig)
        err_msg = (
            "Could not get assessment workflow with submission_uuid {} due to error: {}"
            .format(submission_uuid, exc)
        )
        logger.exception(err_msg)
        raise AssessmentWorkflowInternalError(err_msg)

    return workflow

def _serialized_with_details(workflow, assessment_requirements):
    data_dict = AssessmentWorkflowSerializer(workflow).data
    data_dict["status_details"] = workflow.status_details(assessment_requirements)
    return data_dict
