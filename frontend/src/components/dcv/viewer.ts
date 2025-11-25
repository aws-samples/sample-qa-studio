// DCV SDK is loaded as a UMD module and attaches to window.dcv
declare const dcv: any;

function getScaleToFit(sourceWidth: number, sourceHeight: number, destWidth: number, destHeight: number) {
  const scaleX = destWidth / sourceWidth;
  const scaleY = destHeight / sourceHeight;
  return Math.min(scaleX, scaleY);
}

type connection = {
  requestDisplayLayout: Function;
  requestResolution: Function;
  setDisplayScale: Function;
  disconnect: Function;
}

export class LiveViewer {
  private presignedUrl: string;
  private containerId:string;
  private connection: connection | null;
  private desiredWidth: number;
  private desiredHeight: number;
  private currentHeight: number;
  private currentWidth: number;

  constructor(presignedUrl: string, containerId = 'dcv-display') {
    this.presignedUrl = presignedUrl;
    this.containerId = containerId;
    this.connection = null
    this.desiredWidth = 0;
    this.desiredHeight = 0;
    this.currentHeight = 0;
    this.currentWidth = 0;
  }
  httpExtraSearchParamsCallBack(method: string, url:string, body: string, returnType: string) {
    const parsedUrl = new URL(this.presignedUrl);
    const params = parsedUrl.searchParams;
    console.log('[Viewer] Returning auth params:', params.toString());
    return params;
  }
  
  displayLayoutCallback(_callback: Function, serverWidth: number, serverHeight: number, heads: [] = []) {
    console.log(`[Viewer] Display layout callback`);
    if (this.connection) {
      // Only request display if sizes have actually changed
      if (this.desiredWidth > 0 && this.desiredHeight > 0 && (this.currentWidth !== this.desiredWidth || this.currentHeight !== this.desiredHeight)) {
        console.log(`[Viewer] Requesting display layout change from ${this.currentWidth}x${this.currentHeight} to ${this.desiredWidth}x${this.desiredHeight}`);

        const display = document.getElementById(this.containerId);
        this.connection
          .requestDisplayLayout([
            {
              name: 'Main Display',
              rect: {
                x: 0,
                y: 0,
                width: this.desiredWidth,
                height: this.desiredHeight,
              },
              primary: true,
            },
          ])
          .then(() => {
            if(!this.connection) {
              return
            }
            
            this.connection
              .requestResolution(1480, 860)
              .then(() => {
                console.log(`[Viewer] Resolution successfully set to 1480x860`);
                const scale = getScaleToFit(1480, 860, this.desiredWidth, this.desiredHeight);
                this.connection.setDisplayScale(scale).then(() => {
                  console.log(`[Viewer] Scale successfully set to ${scale}`);

                  const canvas = document.getElementById(this.containerId).querySelector('canvas');
                  canvas.style.transformOrigin = `top left`;
                  canvas.style.transform = `scale(${scale})`;
                  this.currentWidth = this.desiredWidth;
                  this.currentHeight = this.desiredHeight;
                });
              })
              .catch((err: any) => {
                console.error('Failed to set resolution:', err);
              });
          });
      }
    }
  }
  async connect() {
    return new Promise((resolve, reject) => {
      if (typeof dcv === 'undefined') {
        reject(new Error('DCV SDK not loaded'));
        return;
      }
      console.log('[Viewer] DCV SDK loaded, version:', dcv.version || 'Unknown');
      console.log('[Viewer] Available DCV methods:', Object.keys(dcv));
      console.log('[Viewer] Presigned URL:', this.presignedUrl);
      // Set debug logging
      if (dcv.setLogLevel) {
        dcv.setLogLevel(dcv.LogLevel.SILENT);
        console.log('[Viewer] DCV log level set to SILENT');
      }

      console.log('[Viewer] Starting authentication...');
      dcv.authenticate(this.presignedUrl, {
        promptCredentials: () => {
          console.warn(
            '[Viewer] DCV requested credentials - should not happen with presigned URL'
          );
        },
        error: (_auth: any, error: any) => {
          console.error('[Viewer] DCV auth error:', error);
          console.error('[Viewer] Error details:', {
            message: error.message || error,
            code: error.code,
            statusCode: error.statusCode,
            stack: error.stack,
          });
          reject(error);
        },
        success: (_auth: any, result:any) => {
          console.log('[Viewer] DCV auth success:', result);
          if (result && result[0]) {
            const { sessionId, authToken } = result[0];
            console.log('[Viewer] Session ID:', sessionId);
            console.log('[Viewer] Auth token received:', authToken ? 'Yes' : 'No');
            this.connectToSession(sessionId, authToken, resolve, reject);
          } else {
            console.error('[Viewer] No session data in auth result');
            reject(new Error('No session data in auth result'));
          }
        },
        httpExtraSearchParams: this.httpExtraSearchParamsCallBack.bind(this),
      });
    });
  }

  connectToSession(sessionId: string, authToken: string, resolve: Function, reject: Function) {
    console.log('[Viewer] Connecting to session:', sessionId);
    const connectOptions = {
      url: this.presignedUrl,
      sessionId: sessionId,
      authToken: authToken,
      divId: this.containerId,
      baseUrl: `${window.location.origin}/dcv/`,
      callbacks: {
        firstFrame: () => {
          console.log('[Viewer] First frame received!');
          resolve(this.connection);
        },
        error: (error: any) => {
          console.error('[Viewer] Connection error:', error);
          reject(error);
        },
        httpExtraSearchParams: this.httpExtraSearchParamsCallBack.bind(this),
        displayLayout: this.displayLayoutCallback.bind(this),
      },
    };

    console.log('[Viewer] Connect options:', connectOptions);
    dcv
      .connect(connectOptions)
      .then((connection) => {
        console.log('[Viewer] Connection established:', connection);
        this.connection = connection;
      })
      .catch((error) => {
        console.error('[Viewer] Connect failed:', error);
        reject(error);
      });
  }

  setDisplaySize(containerWidth: number, containerHeight: number) {
    this.desiredWidth = containerWidth;
    this.desiredHeight = containerHeight;
    if (this.connection) {
      this.displayLayoutCallback(0, 0, []);
    }
  }

  disconnect() {
    if (this.connection) {
      this.connection.disconnect();
      this.connection = {} as connection;
    }
  }
}