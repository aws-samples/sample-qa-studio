import React, { Suspense } from 'react';
import { ContainerLoading } from './LoadingStates';

// Lazy load the code editor and ACE to reduce initial bundle size
const CodeEditorLazy = React.lazy(async () => {
  // Dynamically import ACE and CodeEditor together
  const [ace, { default: CodeEditor }] = await Promise.all([
    import('ace-builds'),
    import('@cloudscape-design/components/code-editor')
  ]);

  // Configure ACE
  ace.config.set('basePath', 'https://cdn.jsdelivr.net/npm/ace-builds@1.43.2/src-noconflict/');
  
  // Import required ACE modules
  await Promise.all([
    import('ace-builds/src-noconflict/mode-python'),
    import('ace-builds/src-noconflict/theme-textmate')
  ]);

  // Return a wrapper component that includes ACE
  return {
    default: (props: any) => <CodeEditor {...props} ace={ace} />
  };
});

interface LazyCodeEditorProps {
  value: string;
  onChange: (event: { detail: { value: string } }) => void;
  language?: string;
  preferences?: any;
  onPreferencesChange?: (event: any) => void;
  editorContentHeight?: number;
  loading?: boolean;
}

export default function LazyCodeEditor(props: LazyCodeEditorProps) {
  return (
    <Suspense fallback={<ContainerLoading title="Code Editor" text="Loading code editor..." />}>
      <CodeEditorLazy {...props} />
    </Suspense>
  );
}

// Preload function for the code editor
export function preloadCodeEditor() {
  return import('ace-builds').then(() => 
    import('@cloudscape-design/components/code-editor')
  );
}