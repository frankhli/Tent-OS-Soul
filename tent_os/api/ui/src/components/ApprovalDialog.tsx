import { ShieldAlert, CheckCircle2, XCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

interface ApprovalDialogProps {
  sessionId: string;
  plan: unknown;
  onApprove: () => void;
  onReject: () => void;
}

export function ApprovalDialog({ sessionId, plan, onApprove, onReject }: ApprovalDialogProps) {
  const [showDetails, setShowDetails] = useState(false);

  const planData = plan as { analysis?: string; steps?: Array<{ step: number; action: string; executor: string; params?: Record<string, unknown> }> } | null;
  const steps = planData?.steps || [];
  const analysis = planData?.analysis || '无详细分析';

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl border border-amber-200 w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="bg-amber-50 px-6 py-4 border-b border-amber-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
              <ShieldAlert className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900">高风险操作需要确认</h3>
              <p className="text-xs text-gray-500">Session: {sessionId.slice(0, 16)}...</p>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-4 max-h-[50vh] overflow-y-auto">
          <p className="text-sm text-gray-600 mb-4">
            AI 制定了一个执行计划，涉及潜在风险操作。请仔细审阅后决定是否执行。
          </p>

          {/* 分析摘要 */}
          <div className="bg-gray-50 rounded-lg p-3 mb-3">
            <p className="text-sm font-medium text-gray-700 mb-1">分析</p>
            <p className="text-sm text-gray-600">{analysis}</p>
          </div>

          {/* 步骤列表 */}
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1 text-sm font-medium text-tent-700 hover:text-tent-800 mb-2"
          >
            {showDetails ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            执行步骤 ({steps.length} 步)
          </button>

          {showDetails && (
            <div className="space-y-2">
              {steps.map((step, i) => (
                <div key={i} className="flex items-start gap-3 bg-gray-50 rounded-lg p-3">
                  <div className="w-6 h-6 rounded-full bg-tent-100 flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-xs font-bold text-tent-700">{step.step}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800">{step.action}</p>
                    <p className="text-xs text-gray-500">执行者: {step.executor}</p>
                    {step.params && Object.keys(step.params).length > 0 && (
                      <pre className="mt-1 p-1.5 bg-white rounded text-xs text-gray-600 overflow-x-auto">
                        {JSON.stringify(step.params, null, 2)}
                      </pre>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex gap-3">
          <button
            onClick={onReject}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-white border border-gray-200 text-gray-700 font-medium hover:bg-gray-100 transition-colors"
          >
            <XCircle className="w-4 h-4" />
            拒绝执行
          </button>
          <button
            onClick={onApprove}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-tent-600 text-white font-medium hover:bg-tent-700 transition-colors"
          >
            <CheckCircle2 className="w-4 h-4" />
            批准执行
          </button>
        </div>
      </div>
    </div>
  );
}
