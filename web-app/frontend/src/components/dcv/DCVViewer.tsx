import { useEffect, useRef, useState } from 'react';
import { LiveViewer } from './viewer';

export interface RemoteBrowserProps {
  presignedUrl: string;
}

export const RemoteBrowser = (props: RemoteBrowserProps) => {
  const [liveStreamUrl, setLiveStreamUrl] = useState('');
  const [viewer, setViewer] = useState<LiveViewer | undefined>(undefined);
  const [size, setSize] = useState({ width: 1480, height: 860 });
  const containerRef = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    setLiveStreamUrl(props.presignedUrl)
    console.log(props.presignedUrl)
  }, [])

  useEffect(() => {
    if (containerRef.current) {
      const rect = containerRef.current?.getBoundingClientRect();
      // setSize({ width: rect.width, height: rect.height });
    }
  }, [containerRef.current]);

  useEffect(() => {
    (async () => {
      console.log('Setting up live stream viewer...');
      try {
        const viewer = new LiveViewer(liveStreamUrl);
        setViewer(viewer);
        await viewer.connect();
      } catch (error) {
        console.error(`Failed to initialze the Live Viewer ${JSON.stringify(error)}`);
      }
    })();
  }, [liveStreamUrl]);

  useEffect(() => {
    if (size.width > 0 && viewer) {
      viewer.setDisplaySize(size.width, size.height);
    }
  }, [JSON.stringify(size), viewer]);
  
  return (
    <div ref={containerRef} className="RemoteBrowserContainer">
      <div id="dcv-display"></div>
    </div>
  );
};