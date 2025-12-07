function setupDataTable(selector){
    const table = $(selector).DataTable({
        orderCellsTop: true,
        fixedHeader: true,
        language: {
            url: 'https://cdn.datatables.net/plug-ins/1.13.8/i18n/ru.json'
        }
    });
    // add filter inputs
    $(selector + ' tfoot th').each(function(){
        const title = $(this).text();
        if(title){
            $(this).html('<input type="text" class="form-control form-control-sm" placeholder="'+title+'" />');
        }
    });
    table.columns().every(function(){
        const that = this;
        $('input', this.footer()).on('keyup change clear', function(){
            if(that.search() !== this.value){
                that.search(this.value).draw();
            }
        });
    });

    return table;
}
