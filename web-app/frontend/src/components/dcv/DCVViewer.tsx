import { useEffect, useRef, useState } from 'react';
import { LiveViewer } from './viewer';

export interface RemoteBrowserProps {
  presignedUrl: string;
}

export const RemoteBrowser = (props: RemoteBrowserProps) => {
  const [liveStreamUrl, setLiveStreamUrl] = useState('');
  const [viewer, setViewer] = useState<LiveViewer | undefined>(undefined);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLiveStreamUrl(props.presignedUrl)
  }, [])

  useEffect(() => {
    if (!wrapperRef.current) return;

    // Observe the fixed-size wrapper (not the DCV container which expands to canvas size).
    // The wrapper inherits the viewport dimensions from WizardLiveView (e.g. 600px height).
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setSize({ width, height });
        }
      }
    });
    observer.observe(wrapperRef.current);

    const rect = wrapperRef.current.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      setSize({ width: rect.width, height: rect.height });
    }

    return () => observer.disconnect();
  }, [wrapperRef.current]);

  useEffect(() => {
    (async () => {
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
    <div ref={wrapperRef} style={{ width: '100%', height: '100%', overflow: 'hidden', position: 'relative' }}>
      <div className="RemoteBrowserContainer">
        <div id="dcv-display"></div>
      </div>
    </div>
  );
};