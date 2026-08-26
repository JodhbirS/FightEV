import { Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import Navbar from './components/Navbar';
import CardPage from './pages/CardPage';
import FightersPage from './pages/FightersPage';
import FighterDetailPage from './pages/FighterDetailPage';

export default function App() {
  const location = useLocation();

  return (
    <div className="app-shell">
      <Navbar />
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<CardPage />} />
          <Route path="/fighters" element={<FightersPage />} />
          <Route path="/fighters/:id" element={<FighterDetailPage />} />
        </Routes>
      </AnimatePresence>
    </div>
  );
}
