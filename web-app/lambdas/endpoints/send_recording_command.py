import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import json
import logging
import os
import uuid

import boto3
from pydantic import ValidationError

from recording_models import RecordingCommandRequest
from utils import create_response, require_scopes, validate_path_id

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

eventbridge = boto3.client('events')


def handler(event, context):
    """
    Send a recording command (start/stop) to the wizard worker via EventBridge.

    The worker polls DynamoDB for commands and relays recording_start / recording_stop
    to the NovaActRecorder Chrome extension through CDP.

    Path Parameters:
        sessionId: The wizard session ID

    Request Body:
        { "action": "recording_start" | "recording_stop" }

    Returns:
        200: { "status": "command_sent", "commandId": "<uuid>" }
        400: Invalid request body or missing sessionId
        403: Insufficient scopes
        500: Failed to emit EventBridge event
    """
    # Validate scopes — recording commands are part of the usecase write workflow
    user_identity, error = require_scopes(event, ['api/usecases.write'])
    if error:
        return error

    # Parse and validate sessionId from path parameters
    session_id, error = validate_path_id(
        event.get('pathParameters', {}).get('sessionId'), 'session ID'
    )
    if error:
        return error

    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return create_response(400, {'error': 'Invalid JSON in request body'})

    # Validate request body against Pydantic model
    try:
        command_request = RecordingCommandRequest(**body)
    except ValidationError as e:
        logger.warning(f"Invalid recording command request: {e}")
        return create_response(400, {
            'error': 'Invalid request body',
            'details': e.errors()
        })

    # Build the command payload (same shape as other wizard commands)
    command_id = str(uuid.uuid4())
    command = {
        'action': command_request.action,
        'sessionId': session_id,
    }

    event_bus_name = os.environ.get('WIZARD_EVENT_BUS_NAME')

    try:
        if event_bus_name:
            # Send to Amazon EventBridge (new approach)
            eventbridge.put_events(
                Entries=[{
                    'Source': 'wizard.commands',
                    'DetailType': 'WizardCommand',
                    'Detail': json.dumps(command),
                    'EventBusName': event_bus_name
                }]
            )
            logger.info(
                f"Recording command '{command_request.action}' sent to EventBridge "
                f"for session {session_id}, commandId={command_id}"
            )
        else:
            # Fallback to Amazon SQS (legacy approach)
            sqs = boto3.client('sqs')
            queue_url = os.environ['WIZARD_QUEUE_URL']
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(command)
            )
            logger.info(
                f"Recording command '{command_request.action}' sent to SQS "
                f"for session {session_id}, commandId={command_id}"
            )

        return create_response(200, {
            'status': 'command_sent',
            'commandId': command_id
        })

    except Exception as e:
        logger.error(f"Error sending recording command: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Failed to send recording command'})
