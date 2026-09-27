import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>('');
  const { logout } = useAuth();

  const handleUpload = async () => {
    if (!file) return;
    setStatus('Uploading...');
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/documents/upload`, {
        method: 'POST',
        body: formData,
      });
      if (response.ok) {
        setStatus('Upload successful!');
      } else {
        setStatus('Upload failed.');
      }
    } catch (e) {
      setStatus('Error connecting to server.');
    }
  };

  return (
    <div style={{ padding: '2rem' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Upload SRS Document</h1>
        <button onClick={logout}>Logout</button>
      </header>
      <div style={{ marginTop: '2rem' }}>
        <input type="file" accept=".pdf,.docx" onChange={e => setFile(e.target.files?.[0] || null)} />
        <button onClick={handleUpload} disabled={!file}>Upload</button>
        {status && <p>{status}</p>}
      </div>
      <p><em>Note: Requirement extraction, embeddings, and LLM classification are stubbed (Week 3+)</em></p>
    </div>
  );
}
