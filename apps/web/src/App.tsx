import { useEffect } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Layout from './components/Layout';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Disclaimer from './pages/Disclaimer';
import Home from './pages/Home';
import Scan from './pages/Scan';
import Result from './pages/Result';
import History from './pages/History';
import Chat from './pages/Chat';

export default function App() {
  const { i18n } = useTranslation();
  useEffect(() => {
    const code = i18n.resolvedLanguage ?? 'en';
    document.documentElement.lang = code;
    // i18next 'changeLanguage' fires this effect via the resolvedLanguage dep.
  }, [i18n.resolvedLanguage]);

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/disclaimer" element={<Disclaimer />} />
        <Route path="/home" element={<Home />} />
        <Route path="/scan" element={<Scan />} />
        <Route path="/result/:diagnosticId" element={<Result />} />
        <Route path="/history" element={<History />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
