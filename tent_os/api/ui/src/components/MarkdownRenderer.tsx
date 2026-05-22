import { useEffect, useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, Check } from 'lucide-react';

interface MarkdownRendererProps {
  content: string;
}

// B3: 动态导入 highlight.js core + 常用语言，避免打包所有语言（~1MB → ~50KB）
let hljsInstance: typeof import('highlight.js').default | null = null;
let hljsLoading: Promise<void> | null = null;

const COMMON_LANGUAGES = [
  'python', 'javascript', 'typescript', 'json', 'yaml', 'bash',
  'markdown', 'html', 'css', 'sql', 'rust', 'go', 'java', 'c', 'cpp',
  'php', 'ruby', 'kotlin', 'swift', 'xml', 'ini', 'dockerfile', 'nginx',
];

async function loadHighlighter() {
  if (hljsInstance) return hljsInstance;
  if (hljsLoading) {
    await hljsLoading;
    return hljsInstance!;
  }

  hljsLoading = (async () => {
    const hljs = (await import('highlight.js/lib/core')).default;
    // 并行加载常用语言
    const langModules = await Promise.all(
      COMMON_LANGUAGES.map(async (name) => {
        try {
          const mod = await import(`highlight.js/lib/languages/${name}`);
          return { name, register: mod.default };
        } catch {
          return null;
        }
      })
    );
    langModules.forEach((m) => {
      if (m && m.register) {
        hljs.registerLanguage(m.name, m.register);
      }
    });
    hljsInstance = hljs;
  })();

  await hljsLoading;
  return hljsInstance!;
}

function CodeBlock({ language, value }: { language?: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const codeRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let mounted = true;
    loadHighlighter().then((hljs) => {
      if (mounted && codeRef.current) {
        hljs.highlightElement(codeRef.current);
      }
    });
    return () => { mounted = false; };
  }, [value, language]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div className="code-block-wrapper group my-3">
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-800 rounded-t-lg">
        <span className="text-[10px] text-gray-400 font-mono">
          {language || 'text'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] text-gray-400 hover:text-white hover:bg-white/10 transition-all"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3" />
              已复制
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              复制
            </>
          )}
        </button>
      </div>
      <pre className="!mt-0 rounded-t-none">
        <code ref={codeRef} className={language ? `language-${language}` : ''}>
          {value}
        </code>
      </pre>
    </div>
  );
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const value = String(children).replace(/\n$/, '');
            if (match) {
              return <CodeBlock language={match[1]} value={value} />;
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children }) {
            // Let CodeBlock handle its own pre, or inline code pass through
            return <>{children}</>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
