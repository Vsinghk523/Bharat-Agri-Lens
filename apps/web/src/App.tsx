import { useEffect } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Layout from './components/Layout';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Disclaimer from './pages/Disclaimer';
import Onboarding from './pages/Onboarding';
import Home from './pages/Home';
import Scan from './pages/Scan';
import Result from './pages/Result';
import History from './pages/History';
import Chat from './pages/Chat';
import Profile from './pages/Profile';
import Settings from './pages/Settings';
import Notifications from './pages/Notifications';
import AdminLabellingQueue from './pages/AdminLabellingQueue';

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
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/home" element={<Home />} />
        <Route path="/scan" element={<Scan />} />
        <Route path="/result/:diagnosticId" element={<Result />} />
        <Route path="/history" element={<History />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/admin/labelling-queue" element={<AdminLabellingQueue />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
