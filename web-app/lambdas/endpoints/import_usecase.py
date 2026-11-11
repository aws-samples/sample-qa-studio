import lambda_init  # noqa: F401 — must be first import (adds dependencies/ to sys.path)

import logging
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4
import boto3
from botocore.exceptions import ClientError
from resource_auth import require_resource_access, app_from_body, new_usecase_owner_fields
from utils import (
    create_response,
    get_table_name,
    get_secret_prefix,
    get_current_timestamp,
    extract_user_identity,
    require_scopes,
)
from platforms import validate_test_platform
from dataset_models import missing_dataset_ids, missing_datasets_response, referenced_dataset_ids
from repeat_validation import needs_sibling_validation, validate_repeat_fields
from step_copy import StepTreeError, copy_step_fields, flatten_imported_steps
from template_expansion import (
    TemplateBundle,
    build_linked_steps,
    is_placeholder,
    load_template_bundle,
    merge_variables,
    placeholder_error,
    placeholder_template_ids,
    template_secret_keys,
)
from template_usage import usage_item

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


@require_resource_access('edit', app_from_body('application_id'), scopes=['api/usecases.write'])
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler to import a usecase from export data.

    The body's top-level application_id (required) names the target app;
    the decorator checks edit on it.
    
    Args:
        event: API Gateway proxy request event
        context: Lambda context
        
    Returns:
        API Gateway proxy response with import result
    """
    try:
        user_identity = extract_user_identity(event)
        
        # Extract user info for created_by tracking
        user_email = user_identity.get('email') or user_identity.get('identity', 'unknown')
        user_sub = user_identity.get('sub', '')
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return create_response(400, {'error': 'Invalid JSON in request body'})
        
        # Validate export version
        export_version = body.get('exportVersion')
        if export_version != '1.0':
            return create_response(400, {
                'success': False,
                'message': 'Unsupported export version'
            })
        
        # Initialize Amazon DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(get_table_name())
        
        # Generate new IDs
        new_usecase_id = str(uuid4())
        now = get_current_timestamp()
        
        # Extract import data
        usecase_data = body.get('usecase', {})
        platform_error = validate_test_platform(usecase_data.get('test_platform', ''))
        if platform_error:
            return platform_error
        steps_data = body.get('steps', [])
        if not isinstance(steps_data, list):
            steps_data = []
        variables_data = body.get('variables', [])
        secrets_data = body.get('secrets', [])
        hooks_data = body.get('hooks')
        region_override = body.get('regionOverride')

        # Template placeholders: validate shape, require the read scope and
        # load every referenced template *before* any write.
        shape_error = placeholder_error(steps_data)
        if shape_error:
            return create_response(400, {'success': False, 'message': shape_error})
        template_ids = placeholder_template_ids(steps_data)
        bundles: Dict[str, TemplateBundle] = {}
        if template_ids:
            _, error = require_scopes(event, ['api/templates.read'])
            if error:
                return error
            missing_templates: List[str] = []
            for template_id in template_ids:
                bundle = load_template_bundle(table, template_id)
                if bundle is None:
                    missing_templates.append(template_id)
                else:
                    bundles[template_id] = bundle
            if missing_templates:
                return create_response(400, {'success': False, 'error': 'Template not found',
                                             'message': f"Template not found: {', '.join(missing_templates)}",
                                             'templateIds': missing_templates})

        # Flatten the (possibly nested) step list, assign ids, remap
        # parent_step_id and validate repeat rules *before* any write.
        try:
            flat_steps = flatten_imported_steps(steps_data)
        except StepTreeError as e:
            return create_response(400, {'success': False, 'message': str(e)})

        new_steps: List[Dict[str, Any]] = []
        templates_applied: List[Dict[str, Any]] = []
        # flat index → index in new_steps (None for placeholders, which have no step of their own)
        new_index_of_flat: List[Optional[int]] = []
        for step, parent_index in flat_steps:
            if is_placeholder(step):
                bundle = bundles[step['template_id']]
                linked = build_linked_steps(bundle, new_usecase_id, len(new_steps) + 1, now)
                new_steps.extend(linked)
                templates_applied.append({
                    'templateId': bundle.template_id, 'version': bundle.version, 'stepsCreated': len(linked),
                })
                new_index_of_flat.append(None)
                continue
            new_step = {
                'pk': f'USECASE#{new_usecase_id}',
                'sk': '',  # filled once the id is known
                'sort': len(new_steps) + 1,  # Reorder sequentially
                'id': str(uuid4()),
                'created_at': now,
                **copy_step_fields(step),
            }
            new_step['sk'] = f"STEP#{new_step['id']}"
            if parent_index is not None:
                new_step['parent_step_id'] = new_steps[new_index_of_flat[parent_index]]['id']
            new_index_of_flat.append(len(new_steps))
            new_steps.append(new_step)

        repeat_errors: List[str] = []
        for position, new_step in enumerate(new_steps):
            if needs_sibling_validation(new_step):
                repeat_errors.extend(
                    f'steps[{position}]: {err}' for err in validate_repeat_fields(new_step, new_steps)
                )
        if repeat_errors:
            return create_response(400, {'success': False, 'message': '; '.join(repeat_errors)})

        # Repeat steps that reference an application dataset: the dataset
        # must exist in the *target* application (ids are environment-specific).
        dataset_ids = referenced_dataset_ids(new_steps)
        if dataset_ids:
            missing_datasets = missing_dataset_ids(table, body['application_id'], dataset_ids)
            if missing_datasets:
                return missing_datasets_response(missing_datasets)

        # Template variables join the file's (file wins); template secret
        # keys join the file's secrets (file description wins).
        for template_id in template_ids:
            variables_data = merge_variables(variables_data, bundles[template_id].variables)
        secret_descriptions: Dict[str, str] = {}
        for secret in secrets_data:
            secret_key = secret.get('key', '')
            if secret_key and secret_key not in secret_descriptions:
                secret_descriptions[secret_key] = secret.get('description', '')
        for template_id in template_ids:
            for secret_key in template_secret_keys(bundles[template_id]):
                secret_descriptions.setdefault(secret_key, '')
        
        # Create new usecase with proper pk/sk
        usecase_tags = usecase_data.get('tags', [])
        # Add "imported" tag if not already present
        if 'imported' not in usecase_tags:
            usecase_tags.append('imported')
        
        new_usecase = {
            'pk': 'USECASES',
            'sk': f'USECASE#{new_usecase_id}',
            'id': new_usecase_id,
            'name': usecase_data.get('name', ''),
            'description': usecase_data.get('description', ''),
            'starting_url': usecase_data.get('starting_url', ''),
            'active': usecase_data.get('active', False),
            'executing_region': region_override or usecase_data.get('executing_region', ''),
            'tags': usecase_tags,
            'created_at': now,
            'test_platform': usecase_data.get('test_platform', 'web'),
            **new_usecase_owner_fields(body['application_id']),
        }

        # Add mobile-specific fields if present
        mobile_fields = ['platform', 'app_package', 'app_activity', 'bundle_id', 'device_arn', 'model_id', 'browser_policy_s3_path']
        for field in mobile_fields:
            val = usecase_data.get(field, '')
            if val:
                new_usecase[field] = val
        
        # Save usecase
        table.put_item(Item=new_usecase)
        
        # Save created_by record
        created_by_record = {
            'pk': f'USECASE#{new_usecase_id}',
            'sk': 'CREATED_BY',
            'email': user_email,
            'sub': user_sub,
            'created_at': now
        }
        table.put_item(Item=created_by_record)
        
        # Save steps (ids, parent pointers and sort assigned above)
        for new_step in new_steps:
            try:
                table.put_item(Item=new_step)
            except Exception as e:
                logger.error(f"Error saving step: {str(e)}")

        # One USAGE record per template linked into this use case (reverse
        # index for delete_template); none for plain files.
        for template_id in template_ids:
            table.put_item(Item=usage_item(template_id, new_usecase_id, now))
        
        # Save variables
        if variables_data:
            usecase_variables = {
                'pk': f'USECASE#{new_usecase_id}',
                'sk': 'USECASE_VARIABLES',
                'variables': variables_data,
                'created_at': now
            }
            table.put_item(Item=usecase_variables)
        
        # Save secret placeholders (records only; the value — and the Secrets
        # Manager secret — is created later via POST /usecase/{id}/secrets).
        missing_secrets = []
        for secret_key, description in secret_descriptions.items():
            # Same path as create_usecase_secrets so the secret set later
            # resolves at runtime and matches the IAM scope.
            table.put_item(Item={
                'pk': f'USECASE#{new_usecase_id}',
                'sk': f'SECRET#{secret_key}',
                'key': secret_key,
                'secret_name': f"{get_secret_prefix()}/usecase/{new_usecase_id}/{secret_key}",
                'description': description,
                'created_at': now,
            })
            missing_secrets.append(secret_key)
        
        # Save hooks
        if hooks_data:
            hooks_item = {
                'pk': f'USECASE#{new_usecase_id}',
                'sk': 'HOOKS',
                'before_script': hooks_data.get('beforeScript', ''),
                'after_script': hooks_data.get('afterScript', ''),
                'created_at': now
            }
            
            try:
                table.put_item(Item=hooks_item)
            except Exception as e:
                logger.error(f"Error saving hooks: {str(e)}")
        
        # Create response
        response_data = {
            'success': True,
            'usecaseId': new_usecase_id,
            'message': 'Usecase imported successfully'
        }
        
        if missing_secrets:
            response_data['missingSecrets'] = missing_secrets
        if templates_applied:
            response_data['templatesApplied'] = templates_applied
        
        return create_response(200, response_data)
        
    except Exception as e:
        logger.error(f"Error importing usecase: {str(e)}", exc_info=True)
        return create_response(500, {'error': 'Internal server error'})
