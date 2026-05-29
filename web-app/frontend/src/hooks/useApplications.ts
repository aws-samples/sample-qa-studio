import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import { Application } from '../types/application';

export function useApplications() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await api.get('applications');
        setApplications(Array.isArray(data) ? data : []);
      } catch {
        setApplications([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const options = applications.map(app => ({
    label: app.name,
    value: app.id,
    description: app.base_url,
  }));

  return { applications, options, loading };
}
