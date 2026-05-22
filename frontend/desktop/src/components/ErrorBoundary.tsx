import { Component, ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';

interface Props {
 children: ReactNode;
}

interface State {
 hasError: boolean;
 error?: Error;
}

export default class ErrorBoundary extends Component<Props, State> {
 state: State = { hasError: false };

 static getDerivedStateFromError(error: Error): State {
 return { hasError: true, error };
 }

 render() {
 if (this.state.hasError) {
 return (
 <div className="h-screen flex items-center justify-center bg-surface-base">
 <div className="text-center">
 <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
 <h2 className="text-lg font-medium text-content-secondary mb-2">出错了</h2>
 <p className="text-sm text-content-muted mb-4">页面渲染失败，请刷新重试</p>
 <button
 onClick={() => window.location.reload()}
 className="px-4 py-2 bg-violet-600 text-white rounded-lg text-sm hover:bg-violet-700 transition"
 >
 刷新页面
 </button>
 </div>
 </div>
 );
 }
 return this.props.children;
 }
}
