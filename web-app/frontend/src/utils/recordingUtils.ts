import { api } from './api';

export interface RecordingEvent {
  type: number;
  timestamp: number;
  data: any;
}

export interface RecordingMetadata {
  startTime?: string | number;
  duration?: number;
  durationMs?: number;
  eventCount?: number;
  totalEvents?: number;
}

export interface RecordingBatchList {
  batches: string[];
  metadata: RecordingMetadata;
}

export interface RrwebPlaybackResponse {
  playback_type: "rrweb";
  execution_id: string;
  trigger_type: string;
  batches: string[];
  metadata: RecordingMetadata;
}

export interface VideoFilePlaybackResponse {
  playback_type: "video";
  execution_id: string;
  trigger_type: string;
  download_url: string;
  content_type: string;
  expires_in: number;
}

export type VideoPlaybackResponse = RrwebPlaybackResponse | VideoFilePlaybackResponse;

export interface RecordingBatch {
  events: RecordingEvent[];
  totalCount: number;
  totalPages: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

export const listRecordingBatches = async (
  usecaseId: string,
  executionId: string
): Promise<RecordingBatchList> => {
  try {
    const response = await api.get(`usecase/${usecaseId}/executions/${executionId}/events`);
    return response as RecordingBatchList;
  } catch (error) {
    console.error('Failed to list recording batches:', error);
    throw error;
  }
};

export const getRecordingBatch = async (
  usecaseId: string,
  executionId: string,
  batchId: string,
  page: number = 1,
  pageSize: number = 200
): Promise<RecordingBatch> => {
  try {
    const response = await api.get(
      `usecase/${usecaseId}/executions/${executionId}/event/${batchId}?page=${page}&pageSize=${pageSize}`
    );
    return response as RecordingBatch;
  } catch (error) {
    console.error(`Failed to get recording batch ${batchId} (page ${page}):`, error);
    throw error;
  }
};

export const getVideoPlayback = async (
  usecaseId: string,
  executionId: string
): Promise<VideoPlaybackResponse> => {
  try {
    const response = await api.get(`usecase/${usecaseId}/executions/${executionId}/video`);
    return response as VideoPlaybackResponse;
  } catch (error) {
    console.error('Failed to get video playback:', error);
    throw error;
  }
};

