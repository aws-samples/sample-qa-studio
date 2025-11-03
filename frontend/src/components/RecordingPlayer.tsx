import React, { useEffect, useRef, useState } from 'react';
import { Box, Spinner, Alert, ProgressBar } from '@cloudscape-design/components';
import { listRecordingBatches, getRecordingBatch, RecordingEvent, RecordingMetadata } from '../utils/recordingUtils';

interface RecordingPlayerProps {
  usecaseId: string;
  executionId: string;
}

export const RecordingPlayer: React.FC<RecordingPlayerProps> = ({
  usecaseId,
  executionId,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loadingStatus, setLoadingStatus] = useState('Initializing...');
  const [error, setError] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<RecordingMetadata | null>(null);
  const [backgroundLoading, setBackgroundLoading] = useState(false);
  const [backgroundProgress, setBackgroundProgress] = useState(0);
  const [readyToInitPlayer, setReadyToInitPlayer] = useState(false);
  const playerRef = useRef<any>(null);
  const allEventsRef = useRef<RecordingEvent[]>([]);
  const rrwebPlayerRef = useRef<any>(null);

  useEffect(() => {
    let mounted = true;

    const loadRecording = async () => {
      try {
        setLoading(true);
        setError(null);
        setLoadingStatus('Listing recording batches...');
        setLoadingProgress(0);

        // Step 1: List all batches
        const batchList = await listRecordingBatches(usecaseId, executionId);

        if (!mounted) return;

        if (!batchList.batches || batchList.batches.length === 0) {
          setError('No recording batches found');
          setLoading(false);
          return;
        }

        setMetadata(batchList.metadata);
        const totalBatches = batchList.batches.length;
        
        // Step 2: Load first batch to start player quickly
        const firstBatchId = batchList.batches[0];
        
        // First, get the first page to know total pages
        setLoadingStatus(`Loading batch 1/${totalBatches}...`);
        setLoadingProgress(10);
        
        const firstPage = await getRecordingBatch(usecaseId, executionId, firstBatchId, 1);
        allEventsRef.current.push(...firstPage.events);
        const totalPages = firstPage.totalPages;
        
        if (!mounted) return;
        
        // If there are more pages, load them in parallel
        if (totalPages > 1) {
          setLoadingStatus(`Loading batch 1/${totalBatches} (${totalPages} pages in parallel)...`);
          
          // Create array of page numbers to fetch (pages 2 to totalPages)
          const pageNumbers = Array.from({ length: totalPages - 1 }, (_, i) => i + 2);
          const concurrency = 5; // Fetch 5 pages at a time
          
          // Process pages in chunks for controlled concurrency
          for (let i = 0; i < pageNumbers.length; i += concurrency) {
            if (!mounted) return;
            
            const chunk = pageNumbers.slice(i, i + concurrency);
            const progress = 10 + ((i + chunk.length) / totalPages) * 80;
            setLoadingProgress(progress);
            
            // Fetch chunk of pages in parallel
            const pagePromises = chunk.map(pageNum => 
              getRecordingBatch(usecaseId, executionId, firstBatchId, pageNum)
            );
            
            const pageResults = await Promise.all(pagePromises);
            
            // Add all events from this chunk
            pageResults.forEach(result => {
              allEventsRef.current.push(...result.events);
            });
          }
        }

        if (!mounted) return;

        if (allEventsRef.current.length === 0) {
          setError('No recording events found');
          setLoading(false);
          return;
        }

        console.log(`Loaded first batch: ${allEventsRef.current.length} events`);
        
        setLoadingStatus('Sorting events...');
        setLoadingProgress(50);

        // Sort initial events
        allEventsRef.current.sort((a, b) => a.timestamp - b.timestamp);
        
        if (!mounted) return;

        setLoadingStatus('Loading player library...');
        setLoadingProgress(70);

        console.log('Starting rrweb-player import...');
        
        // Step 3: Dynamically import rrweb-player with timeout
        try {
          const importPromise = import('rrweb-player');
          const timeoutPromise = new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Player library import timeout')), 30000)
          );
          
          rrwebPlayerRef.current = await Promise.race([importPromise, timeoutPromise]) as any;
          console.log('rrweb-player imported successfully');
        } catch (importError) {
          console.error('Failed to import rrweb-player:', importError);
          throw new Error(`Failed to load player library: ${importError instanceof Error ? importError.message : 'Unknown error'}`);
        }
        
        if (!mounted) {
          console.log('Component unmounted, aborting');
          return;
        }

        console.log('Data loaded, ready to initialize player');
        setLoadingProgress(100);
        setLoading(false);
        setReadyToInitPlayer(true);
      } catch (err) {
        if (!mounted) return;
        console.error('Error loading recording:', err);
        setError(err instanceof Error ? err.message : 'Failed to load recording');
        setLoading(false);
      }
    };

    loadRecording();

    return () => {
      mounted = false;
      if (playerRef.current) {
        try {
          playerRef.current.$destroy();
        } catch (e) {
          console.error('Error destroying player:', e);
        }
      }
    };
  }, [usecaseId, executionId]);

  // Separate effect to initialize player after container is rendered
  useEffect(() => {
    if (!readyToInitPlayer || !containerRef.current || !rrwebPlayerRef.current) {
      return;
    }

    console.log('Initializing player with container:', containerRef.current);
    console.log('Events to load:', allEventsRef.current.length);

    try {
      // Clear container
      containerRef.current.innerHTML = '';

      // Handle both default and named exports
      const PlayerConstructor = rrwebPlayerRef.current.default || rrwebPlayerRef.current;
      
      if (!PlayerConstructor) {
        throw new Error('Player constructor not found in rrweb-player module');
      }
      
      // Calculate dimensions based on recording aspect ratio
      // Trying landscape: 1296px wide, 864px tall (3:2 ratio)
      const recordingWidth = 1296;
      const recordingHeight = 864;
      const aspectRatio = recordingWidth / recordingHeight; // 1.5
      
      const maxWidth = Math.min(window.innerWidth * 0.9, recordingWidth);
      const maxHeight = window.innerHeight * 0.8;
      
      // Calculate dimensions maintaining aspect ratio
      let width = maxWidth;
      let height = width / aspectRatio; // width / 1.5 (height is smaller than width for landscape)
      
      // If height exceeds max, scale down based on height
      if (height > maxHeight) {
        height = maxHeight;
        width = height * aspectRatio;
      }
      
      console.log(`Player dimensions: ${Math.round(width)}x${Math.round(height)} (aspect ratio: ${aspectRatio.toFixed(2)})`);

      playerRef.current = new PlayerConstructor({
        target: containerRef.current,
        props: {
          events: allEventsRef.current,
          width: width,
          height: height,
          autoPlay: false,
          showController: true,
          speedOption: [1, 2, 4, 8],
        },
      });
      
      console.log('Player created successfully');

      // Start background loading if needed
      const startBackgroundLoading = async () => {
        const batchList = await listRecordingBatches(usecaseId, executionId);
        const totalBatches = batchList.batches.length;

        if (totalBatches > 1) {
          setBackgroundLoading(true);
          
          for (let i = 1; i < totalBatches; i++) {
            const batchId = batchList.batches[i];
            const batchStartLength = allEventsRef.current.length;

            // Get first page to know total pages
            const firstPage = await getRecordingBatch(usecaseId, executionId, batchId, 1);
            allEventsRef.current.push(...firstPage.events);
            const batchTotalPages = firstPage.totalPages;
            
            // Load remaining pages in parallel if there are more
            if (batchTotalPages > 1) {
              const pageNumbers = Array.from({ length: batchTotalPages - 1 }, (_, idx) => idx + 2);
              const concurrency = 5; // Fetch 5 pages at a time
              
              for (let j = 0; j < pageNumbers.length; j += concurrency) {
                const chunk = pageNumbers.slice(j, j + concurrency);
                
                // Calculate progress
                const pagesLoaded = j + chunk.length + 1; // +1 for first page
                const batchBaseProgress = (i / (totalBatches - 1));
                const pageProgress = (pagesLoaded / batchTotalPages) / (totalBatches - 1);
                const totalProgress = Math.round((batchBaseProgress + pageProgress) * 100);
                setBackgroundProgress(totalProgress);
                
                // Fetch chunk in parallel
                const pagePromises = chunk.map(pageNum => 
                  getRecordingBatch(usecaseId, executionId, batchId, pageNum)
                );
                
                const pageResults = await Promise.all(pagePromises);
                pageResults.forEach(result => {
                  allEventsRef.current.push(...result.events);
                });
              }
            }

            const batchEventCount = allEventsRef.current.length - batchStartLength;
            console.log(`Background loaded batch ${i + 1}/${totalBatches}: ${batchEventCount} events (total: ${allEventsRef.current.length})`);
            
            // Re-sort all events
            allEventsRef.current.sort((a, b) => a.timestamp - b.timestamp);
            
            // Update player with new events
            if (playerRef.current && containerRef.current) {
              try {
                // Save current playback state before destroying
                let currentTime = 0;
                let isPlaying = false;
                let playbackSpeed = 1;
                
                try {
                  // Try to get current state from player
                  if (typeof playerRef.current.getCurrentTime === 'function') {
                    currentTime = playerRef.current.getCurrentTime();
                  }
                  // Check if player is currently playing
                  if (playerRef.current.replayer) {
                    isPlaying = playerRef.current.replayer.service?.state?.matches('playing') || false;
                    playbackSpeed = playerRef.current.replayer.config?.speed || 1;
                  }
                  console.log(`Saving player state: time=${currentTime}ms, playing=${isPlaying}, speed=${playbackSpeed}x`);
                } catch (stateError) {
                  console.warn('Could not save player state:', stateError);
                }
                
                // Destroy old player
                playerRef.current.$destroy();
                containerRef.current.innerHTML = '';
                
                // Calculate dimensions based on recording aspect ratio
                const recordingWidth = 1296;
                const recordingHeight = 864;
                const aspectRatio = recordingWidth / recordingHeight; // 1.5
                
                const maxWidth = Math.min(window.innerWidth * 0.9, recordingWidth);
                const maxHeight = window.innerHeight * 0.8;
                
                // Calculate dimensions maintaining aspect ratio
                let width = maxWidth;
                let height = width / aspectRatio;
                
                // If height exceeds max, scale down based on height
                if (height > maxHeight) {
                  height = maxHeight;
                  width = height * aspectRatio;
                }
                
                // Create new player with updated events
                const PlayerConstructor = rrwebPlayerRef.current.default || rrwebPlayerRef.current;
                playerRef.current = new PlayerConstructor({
                  target: containerRef.current,
                  props: {
                    events: allEventsRef.current,
                    width: width,
                    height: height,
                    autoPlay: false,
                    showController: true,
                    speedOption: [1, 2, 4, 8],
                  },
                });
                
                // Restore playback state
                try {
                  // Wait a bit for player to initialize
                  await new Promise(resolve => setTimeout(resolve, 100));
                  
                  if (playerRef.current.replayer) {
                    // Set speed first
                    if (playbackSpeed !== 1 && typeof playerRef.current.setSpeed === 'function') {
                      playerRef.current.setSpeed(playbackSpeed);
                    }
                    
                    // Restore position
                    if (currentTime > 0) {
                      if (typeof playerRef.current.goto === 'function') {
                        playerRef.current.goto(currentTime);
                      } else if (playerRef.current.replayer.goto) {
                        playerRef.current.replayer.goto(currentTime);
                      }
                    }
                    
                    // Resume playing if it was playing
                    if (isPlaying) {
                      if (typeof playerRef.current.play === 'function') {
                        playerRef.current.play();
                      } else if (playerRef.current.replayer.play) {
                        playerRef.current.replayer.play();
                      }
                    }
                    
                    console.log(`Restored player state: time=${currentTime}ms, playing=${isPlaying}, speed=${playbackSpeed}x`);
                  }
                } catch (restoreError) {
                  console.warn('Could not restore player state:', restoreError);
                }
              } catch (updateError) {
                console.error('Error updating player:', updateError);
              }
            }
          }

          setBackgroundLoading(false);
          console.log(`All batches loaded: ${allEventsRef.current.length} total events`);
        }
      };

      startBackgroundLoading().catch(err => {
        console.error('Background loading error:', err);
      });

    } catch (playerError) {
      console.error('Error creating player:', playerError);
      setError(`Failed to initialize player: ${playerError instanceof Error ? playerError.message : 'Unknown error'}`);
    }
  }, [readyToInitPlayer, usecaseId, executionId]);

  if (loading) {
    return (
      <Box textAlign="center" padding="xxl">
        <Spinner size="large" />
        <Box variant="p" padding={{ top: 's' }}>
          {loadingStatus}
        </Box>
        {loadingProgress > 0 && (
          <div style={{ maxWidth: '400px', margin: '0 auto', paddingTop: '8px' }}>
            <ProgressBar value={loadingProgress} />
          </div>
        )}
      </Box>
    );
  }

  if (error) {
    return (
      <Alert type="error" header="Failed to load recording">
        {error}
      </Alert>
    );
  }

  return (
    <Box>
      <div
        ref={containerRef}
        style={{
          width: '100%',
          minHeight: '600px',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center'
        }}
      />
    </Box>
  );
};
