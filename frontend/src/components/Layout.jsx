import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { TrendingUp, BarChart2, Settings, LogOut } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

const navItems = [
  { to: '/', icon: TrendingUp, label: '行情' },
  { to: '/portfolio', icon: BarChart2, label: '持仓' },
  { to: '/settings', icon: Settings, label: '设置' },
]

export default function Layout({ children }) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col w-56 bg-white border-r border-slate-100 fixed inset-y-0 left-0 z-30">
        <div className="flex items-center gap-2 px-5 py-5 border-b border-slate-100">
          <span className="text-2xl">📈</span>
          <div>
            <p className="font-bold text-slate-900 text-sm">AAgent</p>
            <p className="text-xs text-slate-500">量化交易</p>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-blue-50 text-blue-600'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-slate-100">
          <div className="flex items-center gap-2 px-3 py-2 mb-2">
            <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-xs">
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-slate-900 truncate">{user?.username}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-xl transition-all"
          >
            <LogOut size={15} /> 退出登录
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 lg:ml-56 pb-20 lg:pb-0">
        <div className="max-w-5xl mx-auto px-4 py-5">
          {children}
        </div>
      </main>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 bg-white border-t border-slate-100 z-30 pb-safe">
        <div className="flex">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex-1 flex flex-col items-center gap-0.5 py-2 text-xs font-medium transition-all ${
                  isActive ? 'text-blue-600' : 'text-slate-400'
                }`
              }
            >
              <Icon size={20} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
