import unittest
from utils.inventory_order import inventory_order, normalized_history, record_acquisition, record_usage
from utils.rewards import normalize_user_rewards, award_run_rewards


class InventoryPriorityTests(unittest.TestCase):
    def test_equipped_then_acquisition_date_then_frequency_then_stable_others(self):
        entries = [(key, {'type':'skin'}) for key in ('other1','often','older','newest','equipped','other2')]
        data = {'equipped':{'skin':'equipped'}, 'item_history':{
            'often':{'use_count':50}, 'older':{'acquired_at':100,'use_count':90},
            'newest':{'acquired_at':200}}}
        self.assertEqual([key for key,_ in inventory_order(entries,data)],
                         ['equipped','newest','older','often','other1','other2'])

    def test_frequency_resolves_equal_acquisition_dates(self):
        entries = [(key,{'type':'font'}) for key in ('a','b')]
        data = {'item_history':{'a':{'acquired_at':100,'use_count':1},
                                'b':{'acquired_at':100,'use_count':8}}}
        self.assertEqual(inventory_order(entries,data)[0][0],'b')

    def test_all_currently_equipped_categories_take_priority(self):
        entries = [('new',{'type':'header'}),('skin',{'type':'skin'}),('font',{'type':'font'})]
        data = {'equipped':{'skin':'skin','font':'font'},'item_history':{'new':{'acquired_at':999}}}
        self.assertEqual([key for key,_ in inventory_order(entries,data)],['skin','font','new'])

    def test_repeated_acquisition_keeps_original_date_and_usage(self):
        data={}
        record_acquisition(data,'x',now=100)
        record_usage(data,'x')
        record_acquisition(data,'x',now=500)
        self.assertEqual(data['item_history']['x'],{'acquired_at':100,'use_count':1})

    def test_using_legacy_item_does_not_invent_acquisition_date(self):
        data={}
        record_usage(data,'legacy')
        record_usage(data,'legacy')
        self.assertEqual(data['item_history']['legacy'],{'acquired_at':0,'use_count':2})

    def test_invalid_history_cannot_break_sorting(self):
        history={'bad':None,'safe':{'acquired_at':'NaN','use_count':'Infinity'},
                 'negative':{'acquired_at':-1,'use_count':-10}}
        self.assertEqual(normalized_history(history)['safe'],{'acquired_at':0,'use_count':0})
        self.assertEqual(len(inventory_order([('bad',{'type':'skin'})],{'item_history':history})),1)

    def test_reward_normalization_preserves_owned_history_without_backdating(self):
        data=normalize_user_rewards({'unlocked':['game_tetris'],
             'item_history':{'game_tetris':{'acquired_at':123,'use_count':4},'missing':{'use_count':9}}})
        self.assertEqual(data['item_history'],{'game_tetris':{'acquired_at':123,'use_count':4}})
        self.assertEqual(normalize_user_rewards({'unlocked':['game_tetris']})['item_history'],{})

    def test_new_achievement_badges_receive_acquisition_history(self):
        data=normalize_user_rewards({})
        award_run_rewards(data, fresh_documents=1, persist=False)
        self.assertTrue(data['item_history'])
        self.assertTrue(all(item['acquired_at']>0 for item in data['item_history'].values()))


if __name__=='__main__': unittest.main()
