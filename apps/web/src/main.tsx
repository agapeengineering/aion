import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/geist-mono/latin-400.css';
import { App } from './App';
import './style.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
