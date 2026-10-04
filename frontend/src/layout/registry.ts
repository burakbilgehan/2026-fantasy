import type { ComponentType } from 'react'
import { DraftFeed } from '../widgets/draft-feed/DraftFeed'
import { LeagueInfo } from '../widgets/league-info/LeagueInfo'
import { PlayerValues } from '../widgets/player-values/PlayerValues'

export type WidgetDef = {
  id: string
  title: string
  component: ComponentType
  wide?: boolean // spans the full grid row
}

export const widgets: WidgetDef[] = [
  { id: 'player-values', title: 'Player values', component: PlayerValues, wide: true },
  { id: 'draft-feed', title: 'Live draft feed', component: DraftFeed },
  { id: 'league-info', title: 'League', component: LeagueInfo },
]
