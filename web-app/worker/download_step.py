import logging
import os
import boto3
from nova_act import NovaAct
from models import ExecutionStep

logger = logging.getLogger(__name__)

def execute_download_step(nova: NovaAct, step: ExecutionStep, usecase_id: str, execution_id: str, s3_bucket_name: str):
    """Execute a download step to download files from the tested site
    
    Uses CDP Network interception to capture download streams from remote browser.
    """
    logger.info(f"Executing download step {step.sort}: {step.instruction}")
    
    result = None
    success = True
    logs = ''
    downloaded_filename = ''
    cdp_session = None
    download_data = {'file': None, 'filename': None}

    try:
        # Create CDP session for network interception
        logger.info("Creating CDP session for network interception...")
        cdp_session = nova.page.context.new_cdp_session(nova.page)
        
        # Enable Network domain
        cdp_session.send("Network.enable")
        logger.info("Network domain enabled")
        
        # Set up request interception for downloads
        cdp_session.send("Network.setRequestInterception", {
            "patterns": [{
                "urlPattern": "*",
                "interceptionStage": "HeadersReceived"
            }]
        })
        logger.info("Request interception configured")
        
        # Function to download file from intercepted response
        def download_from_stream(interception_id, filename):
            logger.info(f"Downloading file from stream: {filename}")
            temp_path = f"/tmp/{filename}"
            
            try:
                # Get response body as stream
                response = cdp_session.send("Network.takeResponseBodyForInterceptionAsStream", {
                    "interceptionId": interception_id
                })
                stream_handle = response.get("stream")
                
                if not stream_handle:
                    logger.error("No stream handle received")
                    return None
                
                logger.info(f"Stream handle: {stream_handle}")
                
                # Read stream and write to file
                import base64
                bytes_written = 0
                with open(temp_path, 'wb') as f:
                    while True:
                        read_response = cdp_session.send("IO.read", {
                            "handle": stream_handle
                        })
                        
                        if read_response.get("data"):
                            # Decode base64 data and write
                            data = base64.b64decode(read_response["data"])
                            f.write(data)
                            bytes_written += len(data)
                        
                        if read_response.get("eof"):
                            logger.info(f"Stream complete: {bytes_written} bytes written")
                            break
                
                # Close the stream
                try:
                    cdp_session.send("IO.close", {"handle": stream_handle})
                except:
                    pass
                
                logger.info(f"File downloaded to: {temp_path} ({bytes_written} bytes)")
                
                # Abort the request so browser doesn't wait
                try:
                    cdp_session.send("Network.continueInterceptedRequest", {
                        "interceptionId": interception_id,
                        "errorReason": "Aborted"
                    })
                except:
                    pass
                
                return temp_path
                
            except Exception as e:
                logger.error(f"Error downloading from stream: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                return None
        
        # Set up event listener for intercepted requests
        def on_request_intercepted(event):
            try:
                interception_id = event.get("interceptionId")
                request = event.get("request", {})
                response_headers = event.get("responseHeaders", [])
                
                # responseHeaders is a list of {name, value} objects
                # Check if this is a download by looking for Content-Disposition header
                content_disposition = None
                
                if isinstance(response_headers, list):
                    for header in response_headers:
                        if isinstance(header, dict) and header.get("name", "").lower() == "content-disposition":
                            content_disposition = header.get("value", "")
                            break
                elif isinstance(response_headers, dict):
                    # Sometimes it might be a dict
                    content_disposition = response_headers.get("content-disposition") or response_headers.get("Content-Disposition")
                
                # Check if this is a download
                is_download = False
                filename = None
                
                if content_disposition and "attachment" in content_disposition.lower():
                    is_download = True
                    # Extract filename from Content-Disposition header
                    import re
                    import urllib.parse
                    
                    # Try filename*= (RFC 5987) first
                    filename_match = re.search(r"filename\*=(?:UTF-8'')?([^;\s]+)", content_disposition)
                    if filename_match:
                        filename = urllib.parse.unquote(filename_match.group(1))
                    else:
                        # Try regular filename=
                        filename_match = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\s]+)', content_disposition)
                        if filename_match:
                            filename = filename_match.group(1).strip('\'"')
                    
                    # Fallback to URL if still no filename
                    if not filename:
                        url = request.get("url", "")
                        if url:
                            filename = url.split('/')[-1].split('?')[0]
                            filename = urllib.parse.unquote(filename)
                
                if is_download and filename:
                    logger.info(f"Download detected: {filename}")
                    
                    # Download the file
                    file_path = download_from_stream(interception_id, filename)
                    if file_path:
                        download_data['file'] = file_path
                        download_data['filename'] = filename
                else:
                    # Not a download - continue normally
                    try:
                        cdp_session.send("Network.continueInterceptedRequest", {
                            "interceptionId": interception_id
                        })
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error in request intercepted handler: {str(e)}")
                # Continue the request anyway
                try:
                    cdp_session.send("Network.continueInterceptedRequest", {
                        "interceptionId": event.get("interceptionId")
                    })
                except:
                    pass
        
        # Register the event listener
        cdp_session.on("Network.requestIntercepted", on_request_intercepted)
        logger.info("Request intercepted listener registered")
        
        # Execute the instruction to trigger download using expect_download
        logger.info("Executing instruction to trigger download...")
        playwright_download = None
        
        try:
            # Use expect_download to detect the download
            with nova.page.expect_download(timeout=20000) as download_info:
                result = nova.act(step.instruction)
                logger.info("Action executed to trigger download")
            
            playwright_download = download_info.value
            logger.info(f"Playwright detected download: {playwright_download.suggested_filename}")
            
            # Wait a moment to see if CDP also intercepted it
            import time
            time.sleep(1)
            
            if download_data['file']:
                # CDP intercepted it - use that
                logger.info(f"Using CDP intercepted download: {download_data['filename']}")
                temp_path = download_data['file']
                suggested_filename = download_data['filename']
            else:
                # CDP didn't intercept - fetch via HTTP
                logger.info("CDP didn't intercept, fetching via HTTP...")
                download_url = playwright_download.url
                suggested_filename = playwright_download.suggested_filename
                temp_path = f"/tmp/{suggested_filename}"
                
                logger.info(f"Fetching: {download_url}")
                
                # Fetch the file directly via HTTP
                import urllib.request
                import ssl
                
                # Validate URL scheme — only allow http/https to prevent SSRF
                from urllib.parse import urlparse
                parsed = urlparse(download_url)
                if parsed.scheme not in ('http', 'https'):
                    raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
                
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                with urllib.request.urlopen(download_url, context=ssl_context) as response:  # nosec B310
                    with open(temp_path, 'wb') as f:
                        bytes_downloaded = 0
                        chunk_size = 8192
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
                
                logger.info(f"HTTP download complete: {bytes_downloaded} bytes")
                download_data['file'] = temp_path
                download_data['filename'] = suggested_filename
        
        except Exception as e:
            logger.error(f"Download detection failed: {str(e)}")
            raise Exception(f"Failed to detect or download file: {str(e)}")
        
        temp_path = download_data['file']
        suggested_filename = download_data['filename']
        logger.info(f"Download completed: {suggested_filename}")
        
        # Verify the downloaded file exists
        if not os.path.exists(temp_path):
            raise Exception(f"Downloaded file not found at: {temp_path}")
        
        file_size = os.path.getsize(temp_path)
        logger.info(f"Downloaded file size: {file_size} bytes")
        
        if file_size == 0:
            # Wait a bit more and check again
            logger.warning("File size is 0, waiting 3 more seconds...")
            import time
            time.sleep(3)
            file_size = os.path.getsize(temp_path)
            logger.info(f"File size after wait: {file_size} bytes")
            
            if file_size == 0:
                raise Exception(f"Downloaded file is empty (0 bytes): {suggested_filename}")
        
        # Upload to S3
        s3_client = boto3.client('s3')
        s3_key = f"{usecase_id}/{execution_id}/downloads/{suggested_filename}"
        
        s3_client.upload_file(temp_path, s3_bucket_name, s3_key)
        logger.info(f"Uploaded file to S3: s3://{s3_bucket_name}/{s3_key}")
        
        # Clean up temp file
        os.remove(temp_path)
        
        downloaded_filename = suggested_filename
        logs = f"Successfully downloaded: {suggested_filename}"
        
    except TimeoutError as e:
        logger.error(f"Download timeout for step {step.sort}: {str(e)}")
        success = False
        logs = f"Download timeout: {str(e)}"
        
        # Create a minimal result object to prevent None access errors
        from types import SimpleNamespace
        result = SimpleNamespace()
        result.metadata = SimpleNamespace()
        result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"
        
    except Exception as e:
        logger.error(f"Error executing download step {step.sort}: {str(e)}")
        success = False
        logs = f"Download failed: {str(e)}"
        
        # Create a minimal result object to prevent None access errors
        from types import SimpleNamespace
        result = SimpleNamespace()
        result.metadata = SimpleNamespace()
        result.metadata.act_id = e.metadata.act_id if hasattr(e, 'metadata') else "error"
    
    finally:
        # Close CDP session if it was created
        if cdp_session:
            try:
                cdp_session.detach()
                logger.info("CDP session closed")
            except:
                pass
        
        # Close any popup pages that may have been opened
        try:
            for page in nova.page.context.pages:
                if page != nova.page and not page.is_closed():
                    try:
                        page.close()
                        logger.info("Closed popup page")
                    except:
                        pass
        except:
            pass

    status = "success" if success else "error"
    logger.info(f"Download step {step.sort} completed with status: {status}, file: {downloaded_filename}")

    return result, success, logs, downloaded_filename
