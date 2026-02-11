/**
 * CloudFront Function to handle SPA routing
 * This function runs on viewer request and rewrites paths for the SPA
 * 
 * Note: CloudFront Functions have strict limitations:
 * - Must be ES5 compatible (no arrow functions, const/let, etc.)
 * - Maximum size: 10KB
 * - No external dependencies
 * - Limited runtime APIs
 */

function handler(event: any): any {
    var request = event.request;
    var uri = request.uri;
    
    // If the URI starts with /api, pass it through unchanged
    if (uri.startsWith('/api/')) {
        return request;
    }
    
    // If the URI doesn't have a file extension and isn't the root,
    // rewrite it to /index.html for SPA routing
    if (!uri.includes('.') && uri !== '/') {
        request.uri = '/index.html';
    }
    
    // If the URI is empty or just /, serve index.html
    if (uri === '' || uri === '/') {
        request.uri = '/index.html';
    }
    
    return request;
}
