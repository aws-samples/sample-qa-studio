import { Navigate, useParams } from 'react-router-dom';

/**
 * Old execution page URL (`/usecase/:usecaseId/execution/:executionId`) → the
 * use case page with the execution split panel open, so bookmarks keep working.
 */
export default function ExecutionRedirect() {
  const { usecaseId, executionId } = useParams();
  return <Navigate replace to={`/usecase/${usecaseId}?tab=history&execution=${executionId}`} />;
}
