import { api } from './api';

export interface S3DownloadOptions {
  filename?: string;
  openInNewTab?: boolean;
}

export const downloadS3File = async (usecaseId: string, executionId: string, actId: string, fileType: 'html' | 'video' = 'html', options: S3DownloadOptions = {}) => {
  try {
    const requestBody: any = { 
      usecaseId, 
      executionId, 
      fileType
    };
    
    // Only include actId for HTML files
    if (fileType === 'html') {
      requestBody.actId = actId;
    }
    
    const response = await api.post('/generate-s3-url', requestBody);
    const { signedUrl, fileName } = response;
    
    if (options.openInNewTab) {
      // Open in new tab
      window.open(signedUrl, '_blank');
    } else {
      // Download the file
      const link = document.createElement('a');
      link.href = signedUrl;
      link.download = options.filename || fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
    
    return { signedUrl, fileName };
  } catch (error) {
    console.error('Failed to download S3 file:', error);
    throw error;
  }
};

export const getS3FileUrl = async (usecaseId: string, executionId: string, actId: string, fileType: 'html' | 'video' = 'html'): Promise<{signedUrl: string, fileName: string}> => {
  try {
    const requestBody: any = { 
      usecaseId, 
      executionId, 
      fileType
    };
    
    // Only include actId for HTML files
    if (fileType === 'html') {
      requestBody.actId = actId;
    }
    
    const response = await api.post('/generate-s3-url', requestBody);
    return { signedUrl: response.signedUrl, fileName: response.fileName };
  } catch (error) {
    console.error('Failed to get S3 file URL:', error);
    throw error;
  }
};

export const getVideoUrl = async (usecaseId: string, executionId: string): Promise<{signedUrl: string, fileName: string}> => {
  try {
    const response = await api.post('/generate-s3-url', { 
      usecaseId, 
      executionId, 
      fileType: 'video'
    });
    return { signedUrl: response.signedUrl, fileName: response.fileName };
  } catch (error) {
    console.error('Failed to get video URL:', error);
    throw error;
  }
};