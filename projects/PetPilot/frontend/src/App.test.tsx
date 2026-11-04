import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('登录页', () => {
  it('显示品牌名和登录入口', () => {
    localStorage.removeItem('petpilot_token')
    render(<App />)
    expect(screen.getByText('PetPilot')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('验证码')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument()
  })
})
