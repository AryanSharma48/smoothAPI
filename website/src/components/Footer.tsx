export default function Footer() {
  return (
    <footer className="border-t border-slate-800 py-8 px-6 bg-[#070a13]">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-slate-500 text-sm">
        <div>Released under the MIT License. &copy; {new Date().getFullYear()} Aryan Sharma.</div>
        <div className="flex space-x-6">
          <a href="https://www.npmjs.com/package/@codingaryan/smoothapi" target="_blank" rel="noreferrer" className="hover:text-rose-500 transition-colors">NPM Package</a>
          <a href="https://pypi.org/project/smoothapi-py/" target="_blank" rel="noreferrer" className="hover:text-rose-500 transition-colors">PyPI Package</a>
          <a href="https://github.com/AryanSharma48/smoothAPI" target="_blank" rel="noreferrer" className="hover:text-rose-500 transition-colors">GitHub</a>
        </div>
      </div>
    </footer>
  );
}
