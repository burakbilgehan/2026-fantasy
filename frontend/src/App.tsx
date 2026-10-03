import { widgets } from './layout/registry'

export default function App() {
  return (
    <main>
      <h1>2026 Fantasy</h1>
      <div className="grid">
        {widgets.map(({ id, title, component: Widget }) => (
          <section key={id} className="widget">
            <h2>{title}</h2>
            <Widget />
          </section>
        ))}
      </div>
    </main>
  )
}
