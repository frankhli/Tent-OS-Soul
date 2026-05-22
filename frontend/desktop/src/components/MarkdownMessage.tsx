import ReactMarkdown from 'react-markdown';
import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';

interface Props {
  content: string;
}

export default function MarkdownMessage({ content }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback((text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, []);

  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        code: ({ children, className }) => {
          const isInline = !className;
          if (isInline) {
            return <code className="px-1 py-0.5 bg-surface-overlay rounded text-xs font-mono">{children}</code>;
          }
          // Code block — rendered inside pre
          const lang = className?.replace('language-', '') || '';
          return <code className={`${className || ''} text-xs font-mono`}>{children}</code>;
        },
        pre: ({ children }) => {
          // Extract code text for copying
          let codeText = '';
          let lang = '';
          const extract = (node: any): void => {
            if (typeof node === 'string') codeText += node;
            if (typeof node === 'number') codeText += String(node);
            if (node?.props?.children) {
              if (node.props.className) {
                const match = node.props.className.match(/language-(\w+)/);
                if (match) lang = match[1];
              }
              if (Array.isArray(node.props.children)) {
                node.props.children.forEach(extract);
              } else {
                extract(node.props.children);
              }
            }
          };
          extract(children);

          return (
            <div className="relative group mb-2">
              <div className="flex items-center justify-between px-3 py-1.5 bg-surface-overlay rounded-t-lg border border-line-subtle border-b-0">
                <span className="text-[10px] text-content-muted font-mono uppercase">{lang || 'code'}</span>
                <button
                  onClick={() => handleCopy(codeText)}
                  className="flex items-center gap-1 text-[10px] text-content-muted hover:text-content-secondary transition opacity-0 group-hover:opacity-100"
                  title="复制"
                >
                  {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                  {copied ? '已复制' : '复制'}
                </button>
              </div>
              <pre className="p-3 bg-surface-panel rounded-b-lg overflow-x-auto text-xs scrollbar-thin border border-line-subtle border-t-0">
                {children}
              </pre>
            </div>
          );
        },
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-violet-400 pl-3 italic text-content-muted mb-2">
            {children}
          </blockquote>
        ),
        a: ({ children, href }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
