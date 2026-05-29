export interface Application {
  id: string;
  name: string;
  base_url: string;
  description: string;
  team: string;
  environments: string[];
  created_at: string;
  updated_at: string;
  last_execution_id: string;
  last_execution_status: string;
  last_execution_at: string;
  usecase_count: number;
}

export interface ApplicationMetrics {
  application_id: string;
  window: '7d' | '30d';
  environment: string;
  series: {
    dates: string[];
    executions: number[];
    successes: number[];
    failures: number[];
    avg_duration_ms: number[];
  };
  totals: {
    total_executions: number;
    pass_rate: number;
    avg_duration_ms: number;
  };
  health_score: number;
}

export interface ApplicationFailure {
  usecase_id: string;
  usecase_name: string;
  error_message: string;
  execution_id: string;
  environment: string;
  sk: string;
}

export interface FlakyUsecase {
  usecase_id: string;
  usecase_name: string;
  flip_count_7d: number;
  flip_count_30d: number;
  last_flip_at: string;
  last_status: string;
}

export interface DashboardOverviewItem extends Application {
  pass_rate?: number;
  total_executions?: number;
  failure_count?: number;
  series?: {
    dates: string[];
    successes: number[];
    failures: number[];
  };
}
