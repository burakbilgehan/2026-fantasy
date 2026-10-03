import type { ComponentType } from 'react'
import { LeagueInfo } from '../widgets/league-info/LeagueInfo'

export type WidgetDef = {
  id: string
  title: string
  component: ComponentType
}

export const widgets: WidgetDef[] = [
  { id: 'league-info', title: 'League', component: LeagueInfo },
]
