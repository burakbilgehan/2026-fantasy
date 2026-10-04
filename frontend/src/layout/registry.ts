import type { ComponentType } from 'react'
import { DraftFeed } from '../widgets/draft-feed/DraftFeed'
import { LeagueInfo } from '../widgets/league-info/LeagueInfo'

export type WidgetDef = {
  id: string
  title: string
  component: ComponentType
}

export const widgets: WidgetDef[] = [
  { id: 'draft-feed', title: 'Live draft feed', component: DraftFeed },
  { id: 'league-info', title: 'League', component: LeagueInfo },
]
