'use client';

import Link from 'next/link';
import {
  BarChart3,
  BookOpenText,
  BrainCircuit,
  FlaskConical,
  LogIn,
  LogOut,
  ShieldCheck,
  UserPlus,
} from 'lucide-react';

import type { WorkspaceView } from './types';

interface AcademicTopbarProps {
  activeView: WorkspaceView;
  onViewChange: (view: WorkspaceView) => void;
  userId: string;
  password: string;
  authenticated: boolean;
  authReady: boolean;
  onUserIdChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onLogin: () => void;
  onRegister: () => void;
  onLogout: () => void;
}

export function AcademicTopbar({
  activeView,
  onViewChange,
  userId,
  password,
  authenticated,
  authReady,
  onUserIdChange,
  onPasswordChange,
  onLogin,
  onRegister,
  onLogout,
}: AcademicTopbarProps) {
  return (
    <header className="workspace-topbar">
      <div className="workspace-topbar-inner">
        <button
          type="button"
          className="workspace-brand"
          onClick={() => onViewChange('studio')}
          aria-label="Open Problem Studio"
        >
          <span className="workspace-brand-seal"><BrainCircuit size={19} /></span>
          <span>
            <strong>Calculus Atelier</strong>
            <small>Reasoning Studio</small>
          </span>
        </button>

        <nav className="workspace-nav" aria-label="Primary workspace navigation">
          <button
            type="button"
            className={activeView === 'studio' ? 'is-active' : ''}
            onClick={() => onViewChange('studio')}
            aria-current={activeView === 'studio' ? 'page' : undefined}
          >
            <BookOpenText size={15} /> Problem Studio
          </button>
          <button
            type="button"
            className={activeView === 'agents' ? 'is-active' : ''}
            onClick={() => onViewChange('agents')}
            aria-current={activeView === 'agents' ? 'page' : undefined}
          >
            <FlaskConical size={15} /> Agent Laboratory
          </button>
          <Link href="/dashboard" aria-label="Progress Report">
            <BarChart3 size={15} /> Progress
          </Link>
        </nav>

        <div className="workspace-auth" aria-label="Account controls">
          {authenticated ? (
            <>
              <span className="workspace-authenticated">
                <ShieldCheck size={15} /> {userId}
              </span>
              <button type="button" onClick={onLogout} aria-label="Sign out">
                <LogOut size={15} /> <span>Sign out</span>
              </button>
            </>
          ) : (
            <>
              <input
                type="text"
                aria-label="User ID"
                placeholder="User ID"
                value={userId}
                onChange={(event) => onUserIdChange(event.target.value)}
              />
              <input
                type="password"
                aria-label="Password"
                placeholder="Password"
                value={password}
                onChange={(event) => onPasswordChange(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && onLogin()}
              />
              <button type="button" onClick={onLogin} disabled={!authReady} aria-label="Sign in">
                <LogIn size={15} /> <span>Sign in</span>
              </button>
              <button
                type="button"
                onClick={onRegister}
                disabled={!authReady}
                className="workspace-register"
                aria-label="Register"
              >
                <UserPlus size={15} /> <span>Register</span>
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
