import CodeBlock from "@/components/CodeBlock";

export default function InstallationPage() {
  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">Installation</h2>
      <div className="space-y-6">
        <div>
          <h4 className="text-slate-300 font-semibold mb-2">TypeScript/JavaScript (NPM):</h4>
          <CodeBlock language="bash" code="npm install @codingaryan/smoothapi" />
        </div>
        <div>
          <h4 className="text-slate-300 font-semibold mb-2">Python (PyPI):</h4>
          <CodeBlock language="bash" code="pip install smoothapi-py" />
        </div>
      </div>
    </div>
  );
}
