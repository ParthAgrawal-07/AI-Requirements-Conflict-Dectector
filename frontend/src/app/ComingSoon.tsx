/** Placeholder for screens of later sprints, so every sidebar route renders (Sprint 0 check). */
export function ComingSoon({ title, sprint }: { title: string; sprint: string }) {
  return (
    <div className="page">
      <h1>{title}</h1>
      <p className="empty-state card">Arrives in {sprint}.</p>
    </div>
  );
}
