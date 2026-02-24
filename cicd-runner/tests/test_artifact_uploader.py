"""Unit tests for ArtifactUploader class."""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, mock_open
from src.execution.artifact_uploader import ArtifactUploader


class TestArtifactUploader:
    """Test ArtifactUploader functionality."""
    
    def test_init(self):
        """Test ArtifactUploader initialization."""
        api_client = Mock()
        uploader = ArtifactUploader(api_client)
        assert uploader.api_client == api_client
    
    def test_get_content_type_webm(self):
        """Test content type detection for .webm files."""
        path = Path("recording.webm")
        content_type = ArtifactUploader._get_content_type(path)
        assert content_type == "video/webm"
    
    def test_get_content_type_txt(self):
        """Test content type detection for .txt files."""
        path = Path("logs.txt")
        content_type = ArtifactUploader._get_content_type(path)
        assert content_type == "text/plain"
    
    def test_get_content_type_png(self):
        """Test content type detection for .png files."""
        path = Path("screenshot.png")
        content_type = ArtifactUploader._get_content_type(path)
        assert content_type == "image/png"
    
    def test_get_content_type_json(self):
        """Test content type detection for .json files."""
        path = Path("trace.json")
        content_type = ArtifactUploader._get_content_type(path)
        assert content_type == "application/json"
    
    def test_get_content_type_html(self):
        """Test content type detection for .html files (Nova Act traces)."""
        path = Path("trace.html")
        content_type = ArtifactUploader._get_content_type(path)
        assert content_type == "text/html"
    
    def test_get_content_type_unknown(self):
        """Test content type detection for unknown file types."""
        path = Path("unknown.xyz")
        content_type = ArtifactUploader._get_content_type(path)
        assert content_type == "application/octet-stream"
    
    def test_get_content_type_case_insensitive(self):
        """Test content type detection is case insensitive."""
        path = Path("recording.WEBM")
        content_type = ArtifactUploader._get_content_type(path)
        assert content_type == "video/webm"
    
    @pytest.mark.asyncio
    async def test_upload_execution_artifacts_success(self):
        """Test successful upload of execution artifacts."""
        # Mock API client
        api_client = Mock()
        api_client.post = Mock(return_value={
            'upload_url': 'https://s3.amazonaws.com/test-bucket/artifact',
            'artifact_id': 'test-artifact-id'
        })
        
        uploader = ArtifactUploader(api_client)
        
        # Mock the private upload method
        uploader._upload_execution_artifact = AsyncMock()
        
        # Test data
        artifacts = {
            'recording': Path('/tmp/recording.webm'),
            'logs': Path('/tmp/logs.txt')
        }
        
        # Execute
        await uploader.upload_execution_artifacts(
            usecase_id='test-usecase',
            execution_id='test-execution',
            artifacts=artifacts
        )
        
        # Verify both artifacts were uploaded
        assert uploader._upload_execution_artifact.call_count == 2
    
    @pytest.mark.asyncio
    async def test_upload_execution_artifacts_continues_on_error(self):
        """Test that upload continues even if one artifact fails."""
        api_client = Mock()
        uploader = ArtifactUploader(api_client)
        
        # Mock the private upload method to fail on first call, succeed on second
        uploader._upload_execution_artifact = AsyncMock(
            side_effect=[Exception("Upload failed"), None]
        )
        
        artifacts = {
            'recording': Path('/tmp/recording.webm'),
            'logs': Path('/tmp/logs.txt')
        }
        
        # Execute - should not raise exception
        await uploader.upload_execution_artifacts(
            usecase_id='test-usecase',
            execution_id='test-execution',
            artifacts=artifacts
        )
        
        # Verify both uploads were attempted
        assert uploader._upload_execution_artifact.call_count == 2
    
    @pytest.mark.asyncio
    async def test_upload_step_artifacts_success(self):
        """Test successful upload of step artifacts."""
        api_client = Mock()
        uploader = ArtifactUploader(api_client)
        
        # Mock the private upload method
        uploader._upload_step_artifact = AsyncMock()
        
        artifacts = {
            'screenshot': Path('/tmp/screenshot.png'),
            'trace': Path('/tmp/trace.json')
        }
        
        # Execute
        await uploader.upload_step_artifacts(
            usecase_id='test-usecase',
            execution_id='test-execution',
            step_id='test-step',
            artifacts=artifacts
        )
        
        # Verify both artifacts were uploaded
        assert uploader._upload_step_artifact.call_count == 2
    
    @pytest.mark.asyncio
    async def test_upload_step_artifacts_continues_on_error(self):
        """Test that step upload continues even if one artifact fails."""
        api_client = Mock()
        uploader = ArtifactUploader(api_client)
        
        # Mock the private upload method to fail on first call
        uploader._upload_step_artifact = AsyncMock(
            side_effect=[Exception("Upload failed"), None]
        )
        
        artifacts = {
            'screenshot': Path('/tmp/screenshot.png'),
            'trace': Path('/tmp/trace.json')
        }
        
        # Execute - should not raise exception
        await uploader.upload_step_artifacts(
            usecase_id='test-usecase',
            execution_id='test-execution',
            step_id='test-step',
            artifacts=artifacts
        )
        
        # Verify both uploads were attempted
        assert uploader._upload_step_artifact.call_count == 2
    
    @pytest.mark.asyncio
    async def test_upload_execution_artifact_makes_correct_api_call(self):
        """Test that _upload_execution_artifact makes correct API call."""
        # Mock API client
        api_client = Mock()
        api_client.post = Mock(return_value={
            'upload_url': 'https://s3.amazonaws.com/test-bucket/artifact',
            'artifact_id': 'test-artifact-id'
        })
        api_client.patch = Mock(return_value={'upload_status': 'uploaded'})
        
        uploader = ArtifactUploader(api_client)
        
        # Create a temporary file
        test_file = Path('/tmp/test_recording.webm')
        
        # Mock file operations and requests
        with patch('builtins.open', mock_open(read_data=b'test data')):
            with patch('requests.put') as mock_put:
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_put.return_value = mock_response
                
                # Execute
                await uploader._upload_execution_artifact(
                    usecase_id='test-usecase',
                    execution_id='test-execution',
                    artifact_type='recording',
                    artifact_path=test_file
                )
        
        # Verify API call was made with correct parameters
        api_client.post.assert_called_once()
        call_args = api_client.post.call_args
        assert call_args[0][0] == '/usecase/test-usecase/executions/test-execution/artifacts'
        assert call_args[0][1]['type'] == 'recording'
        assert call_args[0][1]['filename'] == 'test_recording.webm'
        assert call_args[0][1]['content_type'] == 'video/webm'
        
        # Verify confirm call was made
        api_client.patch.assert_called_once_with(
            '/usecase/test-usecase/executions/test-execution/artifacts/test-artifact-id',
            {}
        )
    
    @pytest.mark.asyncio
    async def test_upload_execution_artifact_confirm_failure_does_not_raise(self):
        """Test that confirm failure doesn't prevent upload from succeeding."""
        api_client = Mock()
        api_client.post = Mock(return_value={
            'upload_url': 'https://s3.amazonaws.com/test-bucket/artifact',
            'artifact_id': 'test-artifact-id'
        })
        api_client.patch = Mock(side_effect=Exception("Confirm failed"))
        
        uploader = ArtifactUploader(api_client)
        test_file = Path('/tmp/test_recording.webm')
        
        with patch('builtins.open', mock_open(read_data=b'test data')):
            with patch('requests.put') as mock_put:
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_put.return_value = mock_response
                
                # Should not raise despite confirm failure
                await uploader._upload_execution_artifact(
                    usecase_id='test-usecase',
                    execution_id='test-execution',
                    artifact_type='recording',
                    artifact_path=test_file
                )
        
        # Upload still happened
        api_client.post.assert_called_once()
        api_client.patch.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_execution_artifact_no_artifact_id_skips_confirm(self):
        """Test that confirm is skipped when no artifact_id returned."""
        api_client = Mock()
        api_client.post = Mock(return_value={
            'upload_url': 'https://s3.amazonaws.com/test-bucket/artifact'
            # No artifact_id
        })
        
        uploader = ArtifactUploader(api_client)
        test_file = Path('/tmp/test_recording.webm')
        
        with patch('builtins.open', mock_open(read_data=b'test data')):
            with patch('requests.put') as mock_put:
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_put.return_value = mock_response
                
                await uploader._upload_execution_artifact(
                    usecase_id='test-usecase',
                    execution_id='test-execution',
                    artifact_type='recording',
                    artifact_path=test_file
                )
        
        # Confirm should NOT have been called
        api_client.patch.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_upload_step_artifact_makes_correct_api_call(self):
        """Test that _upload_step_artifact makes correct API call."""
        # Mock API client
        api_client = Mock()
        api_client.post = Mock(return_value={
            'upload_url': 'https://s3.amazonaws.com/test-bucket/artifact',
            'artifact_id': 'test-step-artifact-id'
        })
        api_client.patch = Mock(return_value={'upload_status': 'uploaded'})
        
        uploader = ArtifactUploader(api_client)
        
        # Create a temporary file
        test_file = Path('/tmp/test_screenshot.png')
        
        # Mock file operations and requests
        with patch('builtins.open', mock_open(read_data=b'test data')):
            with patch('requests.put') as mock_put:
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_put.return_value = mock_response
                
                # Execute
                await uploader._upload_step_artifact(
                    usecase_id='test-usecase',
                    execution_id='test-execution',
                    step_id='test-step',
                    artifact_type='screenshot',
                    artifact_path=test_file
                )
        
        # Verify API call was made with correct parameters
        api_client.post.assert_called_once()
        call_args = api_client.post.call_args
        assert call_args[0][0] == '/usecase/test-usecase/executions/test-execution/steps/test-step/artifacts'
        assert call_args[0][1]['filename'] == 'test_screenshot.png'
        assert call_args[0][1]['content_type'] == 'image/png'
        
        # Verify confirm call was made
        api_client.patch.assert_called_once_with(
            '/usecase/test-usecase/executions/test-execution/artifacts/test-step-artifact-id',
            {}
        )
    
    @pytest.mark.asyncio
    async def test_upload_step_artifact_confirm_failure_does_not_raise(self):
        """Test that step artifact confirm failure doesn't prevent upload."""
        api_client = Mock()
        api_client.post = Mock(return_value={
            'upload_url': 'https://s3.amazonaws.com/test-bucket/artifact',
            'artifact_id': 'test-step-artifact-id'
        })
        api_client.patch = Mock(side_effect=Exception("Confirm failed"))
        
        uploader = ArtifactUploader(api_client)
        test_file = Path('/tmp/test_screenshot.png')
        
        with patch('builtins.open', mock_open(read_data=b'test data')):
            with patch('requests.put') as mock_put:
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_put.return_value = mock_response
                
                # Should not raise despite confirm failure
                await uploader._upload_step_artifact(
                    usecase_id='test-usecase',
                    execution_id='test-execution',
                    step_id='test-step',
                    artifact_type='screenshot',
                    artifact_path=test_file
                )
        
        api_client.post.assert_called_once()
        api_client.patch.assert_called_once()


class TestUploadSuiteArtifacts:
    """Test suite artifact upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_suite_artifacts_calls_suite_endpoint(self):
        """Verify upload_suite_artifacts POSTs to the correct suite artifact API path."""
        api_client = Mock()
        api_client.post = Mock(return_value={
            'upload_url': 'https://s3.amazonaws.com/bucket/suites/s1/se1/suite_logs.txt',
            'expires_in': 3600,
            's3_key': 'suites/s1/se1/suite_logs.txt',
        })

        uploader = ArtifactUploader(api_client)
        uploader._upload_suite_artifact = AsyncMock()

        artifacts = {'logs': Path('/tmp/suite_logs.txt')}

        await uploader.upload_suite_artifacts(
            suite_id='suite-123',
            suite_execution_id='exec-456',
            artifacts=artifacts,
        )

        uploader._upload_suite_artifact.assert_called_once_with(
            suite_id='suite-123',
            suite_execution_id='exec-456',
            artifact_type='logs',
            artifact_path=Path('/tmp/suite_logs.txt'),
        )

    @pytest.mark.asyncio
    async def test_upload_suite_artifact_retry_on_failure(self):
        """Verify _upload_suite_artifact retries up to 3 times on failure."""
        from tenacity import RetryError

        api_client = Mock()
        api_client.post = Mock(side_effect=Exception("API error"))

        uploader = ArtifactUploader(api_client)
        test_file = Path('/tmp/suite_logs.txt')

        with pytest.raises(RetryError):
            await uploader._upload_suite_artifact(
                suite_id='suite-123',
                suite_execution_id='exec-456',
                artifact_type='logs',
                artifact_path=test_file,
            )

        # tenacity retries 3 times total
        assert api_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_upload_suite_artifact_uploads_to_presigned_url(self):
        """Verify _upload_suite_artifact PUTs the file to the presigned S3 URL."""
        api_client = Mock()
        api_client.post = Mock(return_value={
            'upload_url': 'https://s3.amazonaws.com/bucket/suites/s1/se1/suite_logs.txt',
            'expires_in': 3600,
            's3_key': 'suites/s1/se1/suite_logs.txt',
        })

        uploader = ArtifactUploader(api_client)
        test_file = Path('/tmp/suite_logs.txt')

        with patch('builtins.open', mock_open(read_data=b'log content')):
            with patch('requests.put') as mock_put:
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_put.return_value = mock_response

                await uploader._upload_suite_artifact(
                    suite_id='suite-123',
                    suite_execution_id='exec-456',
                    artifact_type='logs',
                    artifact_path=test_file,
                )

        # Verify POST to correct suite endpoint
        api_client.post.assert_called_once_with(
            '/test-suites/suite-123/executions/exec-456/artifacts',
            {
                'type': 'logs',
                'filename': 'suite_logs.txt',
                'content_type': 'text/plain',
            },
        )

        # Verify PUT to presigned URL with correct content type
        mock_put.assert_called_once()
        put_call = mock_put.call_args
        assert put_call[0][0] == 'https://s3.amazonaws.com/bucket/suites/s1/se1/suite_logs.txt'
        assert put_call[1]['headers'] == {'Content-Type': 'text/plain'}

        # Verify no DynamoDB confirm step (no patch call)
        assert not hasattr(api_client, 'patch') or not api_client.patch.called

    @pytest.mark.asyncio
    async def test_upload_suite_artifact_logs_error_on_failure(self):
        """Verify upload_suite_artifacts logs error but does not raise on failure."""
        api_client = Mock()
        uploader = ArtifactUploader(api_client)

        # Mock _upload_suite_artifact to always fail
        uploader._upload_suite_artifact = AsyncMock(
            side_effect=Exception("Upload failed after retries")
        )

        artifacts = {'logs': Path('/tmp/suite_logs.txt')}

        with patch('src.execution.artifact_uploader.logger') as mock_logger:
            # Should NOT raise
            await uploader.upload_suite_artifacts(
                suite_id='suite-123',
                suite_execution_id='exec-456',
                artifacts=artifacts,
            )

            # Verify error was logged
            mock_logger.error.assert_called_once()
            assert 'suite logs artifact' in mock_logger.error.call_args[0][0]

