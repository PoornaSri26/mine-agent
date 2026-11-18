/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import { TopNavBar } from './components/TopNavBar';
import { Footer } from './components/Footer';
import { HomeScreen } from './components/HomeScreen';
import { ChatScreen } from './components/ChatScreen';
import { AlertsScreen } from './components/AlertsScreen';
import { AuditScreen } from './components/AuditScreen';
import { AgentsScreen } from './components/AgentsScreen';
import { motion, AnimatePresence } from 'motion/react';

/**
 * This review build has no sign-in: the workspace opens immediately and the API
 * scopes conversations to the browser's guest id (see `services/api.ts`).
 * `components/AuthScreen.tsx` and `contexts/AuthContext.tsx` are kept untouched
 * so authentication can be wired back in at the end, as agreed.
 */
export default function App() {
  const [activeTab, setActiveTab] = useState('home');

  const renderScreen = () => {
    switch (activeTab) {
      case 'home':
        return <HomeScreen onLaunch={() => setActiveTab('alerts')} />;
      case 'chatbot':
        return <ChatScreen />;
      case 'alerts':
        return <AlertsScreen />;
      case 'reports':
        return <AuditScreen />;
      case 'agents':
        return <AgentsScreen />;
      default:
        return <HomeScreen onLaunch={() => setActiveTab('chatbot')} />;
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-black text-on-surface">
      <TopNavBar activeTab={activeTab} setActiveTab={setActiveTab} />
      
      <main className={`flex-grow ${activeTab === 'home' ? '' : 'max-w-10xl mx-auto w-full px-4 md:px-10 lg:px-20 xl:px-40 pt-20'}`}>
        {/* No mode="wait": waiting for the exit animation blocks the next screen
            when requestAnimationFrame is throttled (background tab), which froze
            navigation. The screens cross-fade instead. */}
        <AnimatePresence initial={false}>
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
          >
            {renderScreen()}
          </motion.div>
        </AnimatePresence>
      </main>

      <Footer />
    </div>
  );
}
